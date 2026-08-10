from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from collections.abc import Awaitable, Callable, Sequence
from contextlib import suppress
from functools import partial
from pathlib import Path
from time import perf_counter
from typing import Literal, TypeVar, cast

from dotenv import load_dotenv
from openai import AsyncOpenAI

from desk_pet.agent.client import OpenAIModelClient
from desk_pet.agent.connectors import OAuthConnectorLoader, connector_tools_from_environment
from desk_pet.agent.loop import AgentLoop
from desk_pet.agent.prompts import DESK_PET_INSTRUCTIONS
from desk_pet.audio.errors import AudioCancelled, AudioError
from desk_pet.audio.openai_services import OpenAISpeechSynthesizer, OpenAITranscriptionService
from desk_pet.audio.realtime import (
    OpenAIRealtimeVoice,
    RealtimeVoiceResult,
    RealtimeVoiceService,
    RealtimeVoiceTiming,
    StreamingRealtimeVoiceService,
)
from desk_pet.audio.speech_text import text_for_speech
from desk_pet.audio.thinking import ThinkingAudio, ThinkingAudioController
from desk_pet.auth.http import UrllibOAuthHTTPClient
from desk_pet.auth.oauth import OAuthManager
from desk_pet.auth.store import CredentialStoreError, credential_store_from_environment
from desk_pet.config import AppConfig, ConfigError, load_config
from desk_pet.conversation import ConversationError, ConversationService
from desk_pet.events import Event, EventBus, EventType
from desk_pet.hardware.desktop.keyboard_trigger import KeyboardTrigger
from desk_pet.hardware.desktop.opencv_camera import OpenCVCameraDevice
from desk_pet.hardware.desktop.preview_face import DesktopPreviewFace
from desk_pet.hardware.desktop.simulated_face import TerminalFace
from desk_pet.hardware.desktop.sounddevice_audio import SoundDevicePlayer, SoundDeviceRecorder
from desk_pet.hardware.interfaces import (
    AudioOutputControl,
    AudioPlayer,
    AudioRecorder,
    CancellationToken,
    FaceDevice,
    ManagedAudioPlayer,
    SpeechSynthesizer,
    StreamingAudioPlayer,
    StreamingAudioRecorder,
    StreamingSpeechSynthesizer,
    TranscriptionService,
    TriggerDevice,
)
from desk_pet.hardware.linux.evdev_trigger import EvdevKeyStateReader
from desk_pet.integrations.outlook_classic import (
    WindowsOutlookClassicService,
    outlook_classic_installed,
)
from desk_pet.latency import VoiceLatencySample, VoiceLatencyTracker, format_voice_latency
from desk_pet.memory.context import (
    ContextDocumentError,
    build_context_instructions,
    build_realtime_context_instructions,
    load_runtime_context,
)
from desk_pet.memory.conversation_store import ConversationStore
from desk_pet.skills.defaults import create_default_skill_registry
from desk_pet.state_machine import PetState, StateMachine

LOGGER = logging.getLogger(__name__)
InteractionMode = Literal["text", "voice"]
T = TypeVar("T")

BRIEFING_PROMPT = (
    "Give me a concise What's up briefing. Check the current local time and weather, "
    "my upcoming calendar, important recent messages, active timers, and one genuinely "
    "interesting thing happening in Toronto. Use available tools and say clearly when a "
    "source is not connected. Prioritize what affects me today."
)
VISUAL_PROMPT = (
    "What are you looking at? Capture exactly one current camera frame, inspect it, and "
    "tell me concisely what you see."
)


class DeskPetApplication:
    def __init__(
        self,
        trigger: TriggerDevice,
        face: FaceDevice,
        conversation: ConversationService | None = None,
        events: EventBus | None = None,
        text_input: Callable[[str], str] = input,
        output: Callable[[str], None] = print,
        interaction_mode: InteractionMode = "text",
        recorder: AudioRecorder | None = None,
        transcriber: TranscriptionService | None = None,
        synthesizer: SpeechSynthesizer | None = None,
        player: AudioPlayer | None = None,
        thinking_audio: ThinkingAudio | None = None,
        output_control: AudioOutputControl | None = None,
        latency_observer: Callable[[VoiceLatencySample], None] | None = None,
        clock: Callable[[], float] = perf_counter,
        volume_overlay_seconds: float = 0.7,
        exit_on_idle_cancel: bool = True,
        realtime_voice: RealtimeVoiceService | None = None,
    ) -> None:
        self.events = events or EventBus()
        self.state = StateMachine(self.events)
        self.trigger = trigger
        self.face = face
        self.conversation = conversation
        self.text_input = text_input
        self.output = output
        self.interaction_mode = interaction_mode
        self.recorder = recorder
        self.transcriber = transcriber
        self.synthesizer = synthesizer
        self.player = player
        self.thinking_audio = thinking_audio
        self.output_control = output_control
        self.latency_observer = latency_observer
        self._clock = clock
        self._volume_overlay_seconds = volume_overlay_seconds
        self.exit_on_idle_cancel = exit_on_idle_cancel
        self.realtime_voice = realtime_voice
        self._pending_action: str | None = None
        self._privacy_sleeping = False
        self._voice_started_at: float | None = None
        self._voice_released_at: float | None = None
        self._transcript_ready_at: float | None = None
        self._response_ready_at: float | None = None
        self._audio_started_at: float | None = None
        self._volume_display_task: asyncio.Task[None] | None = None
        self._volume_display_generation = 0
        voice_components = (recorder, transcriber, synthesizer, player)
        if interaction_mode == "voice" and any(component is None for component in voice_components):
            raise ValueError("Voice mode requires recorder, transcriber, synthesizer, and player")
        self.events.subscribe(self._display_state)
        self.events.subscribe(self._handle_tool_request)

    async def _display_state(self, event: Event) -> None:
        if event.type is EventType.STATE_CHANGED:
            await self.face.set_state(str(event.payload["state"]))

    async def _handle_tool_request(self, event: Event) -> None:
        if event.type is EventType.TOOL_REQUESTED:
            await self.state.transition_to(PetState.USING_TOOL)

    async def run(self) -> None:
        try:
            if self.conversation is not None:
                await self.conversation.initialize()
            if isinstance(self.player, ManagedAudioPlayer):
                try:
                    await self.player.prepare()
                except AudioError:
                    LOGGER.warning("Audio output could not be prewarmed; it will retry on speech")
            if self.realtime_voice is not None:
                try:
                    await self.realtime_voice.start()
                except Exception:
                    LOGGER.warning(
                        "Realtime voice fast lane could not start; using the standard voice lane",
                        exc_info=True,
                    )
                    self.realtime_voice = None
            if self.thinking_audio is not None:
                try:
                    await self.thinking_audio.prepare()
                except AudioError:
                    LOGGER.warning("Thinking filler audio could not be prepared")
            await self._transition_to_resting_state()
            while True:
                if self._pending_action is not None:
                    action, self._pending_action = self._pending_action, None
                else:
                    action = await self.trigger.wait_for_trigger()
                await self.events.emit(Event.create(EventType.TRIGGER_RECEIVED, action=action))
                if action == "shutdown" or (action == "exit" and self.exit_on_idle_cancel):
                    return
                if action == "privacy_toggle":
                    self._privacy_sleeping = not self._privacy_sleeping
                    await self._transition_to_resting_state()
                    self.output(
                        "DeskBob> Privacy sleep enabled."
                        if self._privacy_sleeping
                        else "DeskBob> Privacy sleep disabled."
                    )
                    continue
                if action in {"volume_down", "volume_up", "mute_toggle"}:
                    await self._handle_output_control(action)
                    continue
                if action == "cancel" or self._privacy_sleeping:
                    continue
                if action in {"listen", "listen_start"}:
                    await self._handle_listen()
                elif action == "briefing":
                    await self._handle_prompt(BRIEFING_PROMPT)
                elif action == "visual":
                    await self._handle_prompt(VISUAL_PROMPT)
        finally:
            if self.realtime_voice is not None:
                await self.realtime_voice.close()
            if isinstance(self.player, ManagedAudioPlayer):
                await self.player.close()
            if self._volume_display_task is not None:
                self._volume_display_task.cancel()
                with suppress(asyncio.CancelledError):
                    await self._volume_display_task
            await self.face.close()

    async def _handle_listen(self) -> None:
        self._voice_started_at = self._clock() if self.interaction_mode == "voice" else None
        self._voice_released_at = None
        self._transcript_ready_at = None
        self._response_ready_at = None
        self._audio_started_at = None
        await self.state.transition_to(PetState.LISTENING)
        if self.interaction_mode == "voice" and self.thinking_audio is not None:
            await self.thinking_audio.listen_started()
        if self.conversation is None:
            await asyncio.sleep(0.35)
            await self._transition_to_resting_state()
            return

        if self.interaction_mode == "voice" and self.realtime_voice is not None:
            input_streamed = False
            chunk_handler: Callable[[bytes], Awaitable[None]] | None = None
            if isinstance(self.realtime_voice, StreamingRealtimeVoiceService) and isinstance(
                self.recorder, StreamingAudioRecorder
            ):
                try:
                    await self.realtime_voice.begin_audio_input()
                    chunk_handler = self.realtime_voice.append_audio_input
                    input_streamed = True
                except Exception:
                    LOGGER.warning("Realtime microphone streaming could not start", exc_info=True)
            recording = await self._collect_voice_recording(
                start_thinking_audio=False,
                chunk_handler=chunk_handler,
            )
            if recording is None:
                if input_streamed and isinstance(
                    self.realtime_voice, StreamingRealtimeVoiceService
                ):
                    await self.realtime_voice.cancel_audio_input()
                await self._transition_to_resting_state()
                return
            await self._handle_realtime_recording(recording, input_streamed=input_streamed)
            return

        user_text = await self._collect_user_text()
        if user_text is None:
            await self._stop_thinking_audio()
            await self._transition_to_resting_state()
            return
        if not user_text:
            if self.interaction_mode == "voice":
                self.output("I didn't hear a question. Hold the push-to-talk key while speaking.")
            else:
                self.output("Type a message after pressing the input key.")
            await self._stop_thinking_audio()
            await self._transition_to_resting_state()
            return

        await self.events.emit(Event.create(EventType.TRANSCRIPT_READY, text=user_text))
        await self._handle_prompt(user_text, transcript_already_emitted=True)

    async def _handle_realtime_recording(
        self,
        recording: bytes,
        *,
        input_streamed: bool,
    ) -> None:
        realtime_voice = self.realtime_voice
        conversation = self.conversation
        assert realtime_voice is not None
        assert conversation is not None
        await self.state.transition_to(PetState.THINKING)

        def audio_started() -> None:
            self._audio_started_at = self._clock()
            asyncio.create_task(self.state.transition_to(PetState.SPEAKING))

        try:

            async def operation(cancellation: CancellationToken) -> RealtimeVoiceResult:
                if input_streamed and isinstance(realtime_voice, StreamingRealtimeVoiceService):
                    return await realtime_voice.respond_to_streamed_audio(
                        cancellation,
                        audio_started,
                    )
                return await realtime_voice.respond(
                    recording,
                    cancellation,
                    audio_started,
                )

            completed, result = await self._run_cancellable(operation)
            if not completed or result is None:
                await self._transition_to_resting_state()
                return
        except Exception:
            LOGGER.warning(
                "Realtime voice turn failed; retrying on the standard lane", exc_info=True
            )
            await realtime_voice.close()
            self.realtime_voice = None
            await self._fallback_recording(recording)
            return

        if result.delegated_request is not None:
            user_text = result.user_transcript or result.delegated_request
            self.output(f"You> {user_text}")
            await self.events.emit(Event.create(EventType.TRANSCRIPT_READY, text=user_text))
            if self.thinking_audio is not None:
                await self.thinking_audio.start()
            await self._handle_prompt(result.delegated_request, transcript_already_emitted=True)
            return

        user_text = result.user_transcript or "[voice message]"
        assistant_text = result.assistant_transcript
        if user_text != "[voice message]":
            self.output(f"You> {user_text}")
        if assistant_text:
            self.output(f"DeskBob> {assistant_text}")
            try:
                await conversation.remember_exchange(user_text, assistant_text)
            except ConversationError as exc:
                LOGGER.warning("%s", exc)
        self._report_realtime_latency(self._clock(), result.timing)
        await self._transition_to_resting_state()

    async def _fallback_recording(self, recording: bytes) -> None:
        assert self.transcriber is not None
        try:
            await self.state.transition_to(PetState.TRANSCRIBING)
            transcript = (await self.transcriber.transcribe(recording)).strip()
            self._transcript_ready_at = self._clock()
            if not transcript:
                self.output("I didn't hear a question. Hold the push-to-talk key while speaking.")
                await self._transition_to_resting_state()
                return
            self.output(f"You> {transcript}")
            await self.events.emit(Event.create(EventType.TRANSCRIPT_READY, text=transcript))
            if self.thinking_audio is not None:
                await self.thinking_audio.start()
            await self._handle_prompt(transcript, transcript_already_emitted=True)
        except AudioError as exc:
            await self.state.transition_to(PetState.ERROR)
            self.output(f"DeskBob audio error> {exc}")
            await self._transition_to_resting_state()

    async def _handle_prompt(
        self,
        user_text: str,
        *,
        transcript_already_emitted: bool = False,
    ) -> None:
        conversation = self.conversation
        if conversation is None:
            return
        if not transcript_already_emitted:
            await self.events.emit(Event.create(EventType.TRANSCRIPT_READY, text=user_text))
        await self.state.transition_to(PetState.THINKING)
        model_started = self._clock()
        try:
            if self.interaction_mode == "voice":
                completed, assistant_text = await self._run_cancellable(
                    lambda _cancellation: conversation.reply(user_text)
                )
                if not completed or assistant_text is None:
                    await self._stop_thinking_audio()
                    await self._transition_to_resting_state()
                    return
            else:
                assistant_text = await conversation.reply(user_text)
        except ConversationError as exc:
            await self._stop_thinking_audio()
            await self.state.transition_to(PetState.ERROR)
            self.output(f"DeskBob> {exc}")
            await self._transition_to_resting_state()
            return
        model_seconds = self._clock() - model_started
        self._response_ready_at = self._clock()

        await self.events.emit(Event.create(EventType.RESPONSE_READY, text=assistant_text))
        if self.interaction_mode == "voice":
            assert self.synthesizer is not None
            assert self.player is not None
            if self.output_control is not None and self.output_control.muted:
                await self._stop_thinking_audio()
                self.output(f"DeskBob> {assistant_text}")
                await self._transition_to_resting_state()
                return
            synthesizer = self.synthesizer
            try:
                spoken_text = text_for_speech(assistant_text)
                if not spoken_text:
                    spoken_text = "I put the link in the text window."
                if isinstance(synthesizer, StreamingSpeechSynthesizer) and isinstance(
                    self.player, StreamingAudioPlayer
                ):
                    await self._play_streaming_speech(
                        synthesizer,
                        self.player,
                        spoken_text,
                        assistant_text,
                        model_seconds,
                    )
                    return
                synthesis_started = self._clock()
                completed, speech = await self._run_cancellable(
                    lambda _cancellation: synthesizer.synthesize(spoken_text)
                )
                if not completed or speech is None:
                    await self._stop_thinking_audio()
                    await self._transition_to_resting_state()
                    return
                synthesis_seconds = self._clock() - synthesis_started
                await self._stop_thinking_audio()
                await self.state.transition_to(PetState.SPEAKING)
                self.output(f"DeskBob> {assistant_text}")
                self._audio_started_at = self._clock()
                completed, _ = await self._run_cancellable(partial(self.player.play, speech))
                if not completed:
                    await self._transition_to_resting_state()
                    return
                self._report_latency(
                    model_seconds=model_seconds,
                    synthesis_seconds=synthesis_seconds,
                    playback_finished_at=self._clock(),
                )
            except AudioError as exc:
                await self._stop_thinking_audio()
                await self.state.transition_to(PetState.ERROR)
                self.output(f"DeskBob audio error> {exc}")
        else:
            await self.state.transition_to(PetState.SPEAKING)
            self.output(f"DeskBob> {assistant_text}")
        await self._transition_to_resting_state()

    async def _play_streaming_speech(
        self,
        synthesizer: StreamingSpeechSynthesizer,
        player: StreamingAudioPlayer,
        spoken_text: str,
        assistant_text: str,
        model_seconds: float,
    ) -> None:
        synthesis_started = self._clock()
        synthesis_seconds = 0.0

        def audio_started() -> None:
            nonlocal synthesis_seconds
            self._audio_started_at = self._clock()
            synthesis_seconds = self._audio_started_at - synthesis_started

        await self._stop_thinking_audio()
        await self.state.transition_to(PetState.SPEAKING)
        self.output(f"DeskBob> {assistant_text}")

        async def play(cancellation: CancellationToken) -> None:
            await player.play_pcm_stream(
                synthesizer.synthesize_pcm_stream(spoken_text),
                cancellation,
                audio_started,
            )

        completed, _ = await self._run_cancellable(play)
        if not completed:
            await self._transition_to_resting_state()
            return
        self._report_latency(
            model_seconds=model_seconds,
            synthesis_seconds=synthesis_seconds,
            playback_finished_at=self._clock(),
        )
        await self._transition_to_resting_state()

    async def _collect_user_text(self) -> str | None:
        if self.interaction_mode == "text":
            return (await asyncio.to_thread(self.text_input, "You> ")).strip()

        assert self.transcriber is not None
        recording = await self._collect_voice_recording(start_thinking_audio=True)
        if recording is None:
            return None
        try:
            await self.state.transition_to(PetState.TRANSCRIBING)
            transcript = (await self.transcriber.transcribe(recording)).strip()
            self._transcript_ready_at = self._clock()
            if transcript:
                self.output(f"You> {transcript}")
            return transcript
        except AudioError as exc:
            await self.state.transition_to(PetState.ERROR)
            self.output(f"DeskBob audio error> {exc}")
            return None

    async def _collect_voice_recording(
        self,
        *,
        start_thinking_audio: bool,
        chunk_handler: Callable[[bytes], Awaitable[None]] | None = None,
    ) -> bytes | None:
        recorder = self.recorder
        assert recorder is not None
        try:

            async def record(cancellation: CancellationToken) -> bytes:
                if chunk_handler is not None and isinstance(recorder, StreamingAudioRecorder):
                    return await recorder.record_utterance_stream(
                        cancellation,
                        chunk_handler,
                    )
                return await recorder.record_utterance(cancellation)

            completed, recording = await self._run_cancellable(record, stop_action="listen_stop")
            if not completed or recording is None:
                return None
            self._voice_released_at = self._clock()
            if start_thinking_audio and self.thinking_audio is not None:
                await self.thinking_audio.start()
            return recording
        except AudioError as exc:
            await self.state.transition_to(PetState.ERROR)
            self.output(f"DeskBob audio error> {exc}")
            return None

    async def _handle_output_control(self, action: str) -> None:
        if self.output_control is None:
            return
        if action == "mute_toggle":
            self.output_control.set_muted(not self.output_control.muted)
            await self._transition_to_resting_state()
            self.output("DeskBob> Muted." if self.output_control.muted else "DeskBob> Unmuted.")
            return
        delta = -0.1 if action == "volume_down" else 0.1
        self.output_control.set_volume(self.output_control.volume + delta)
        percent = round(self.output_control.volume * 100)
        await self.face.set_state(f"volume:{percent}")
        self._volume_display_generation += 1
        if self._volume_display_task is None or self._volume_display_task.done():
            self._volume_display_task = asyncio.create_task(self._restore_face_after_volume())
        self.output(f"DeskBob volume: {percent}%")

    async def _restore_face_after_volume(self) -> None:
        while True:
            generation = self._volume_display_generation
            await asyncio.sleep(self._volume_overlay_seconds)
            if generation == self._volume_display_generation:
                break
        await self.face.set_state(self.state.state.value)
        self._volume_display_task = None

    async def _transition_to_resting_state(self) -> None:
        if self._privacy_sleeping:
            target = PetState.SLEEPING
        elif self.output_control is not None and self.output_control.muted:
            target = PetState.MUTED
        else:
            target = PetState.IDLE
        await self.state.transition_to(target)

    def _report_latency(
        self,
        *,
        model_seconds: float,
        synthesis_seconds: float,
        playback_finished_at: float,
    ) -> None:
        milestones = (
            self._voice_started_at,
            self._voice_released_at,
            self._transcript_ready_at,
            self._response_ready_at,
            self._audio_started_at,
        )
        if any(milestone is None for milestone in milestones):
            return
        voice_started_at = cast(float, self._voice_started_at)
        voice_released_at = cast(float, self._voice_released_at)
        transcript_ready_at = cast(float, self._transcript_ready_at)
        response_ready_at = cast(float, self._response_ready_at)
        audio_started_at = cast(float, self._audio_started_at)
        sample = VoiceLatencySample(
            recording_seconds=voice_released_at - voice_started_at,
            transcription_seconds=transcript_ready_at - voice_released_at,
            model_seconds=model_seconds,
            synthesis_seconds=synthesis_seconds,
            playback_seconds=playback_finished_at - audio_started_at,
            release_to_transcript_seconds=transcript_ready_at - voice_released_at,
            release_to_response_seconds=response_ready_at - voice_released_at,
            release_to_audio_seconds=audio_started_at - voice_released_at,
            total_turn_seconds=playback_finished_at - voice_started_at,
        )
        LOGGER.info("%s", format_voice_latency(sample))
        if self.latency_observer is not None:
            self.latency_observer(sample)
        self._voice_started_at = None
        self._voice_released_at = None

    def _report_realtime_latency(
        self,
        playback_finished_at: float,
        timing: RealtimeVoiceTiming | None,
    ) -> None:
        if (
            self._voice_started_at is None
            or self._voice_released_at is None
            or self._audio_started_at is None
        ):
            return
        released = self._voice_released_at
        audio_started = self._audio_started_at
        release_to_audio = audio_started - released
        sample = VoiceLatencySample(
            recording_seconds=released - self._voice_started_at,
            transcription_seconds=0.0,
            model_seconds=release_to_audio,
            synthesis_seconds=0.0,
            playback_seconds=playback_finished_at - audio_started,
            release_to_transcript_seconds=0.0,
            release_to_response_seconds=release_to_audio,
            release_to_audio_seconds=release_to_audio,
            total_turn_seconds=playback_finished_at - self._voice_started_at,
            release_to_commit_seconds=(timing.prepare_and_commit_seconds if timing else 0.0),
            commit_to_server_audio_seconds=(
                timing.commit_to_server_audio_seconds if timing else 0.0
            ),
            server_audio_to_speaker_seconds=(
                timing.server_audio_to_speaker_seconds if timing else 0.0
            ),
            tool_seconds=timing.tool_seconds if timing else 0.0,
        )
        LOGGER.info("Realtime %s", format_voice_latency(sample))
        if self.latency_observer is not None:
            self.latency_observer(sample)
        self._voice_started_at = None
        self._voice_released_at = None

    async def _stop_thinking_audio(self) -> None:
        if self.thinking_audio is not None:
            await self.thinking_audio.stop()

    async def _run_cancellable(
        self,
        operation: Callable[[CancellationToken], Awaitable[T]],
        *,
        stop_action: str | None = None,
    ) -> tuple[bool, T | None]:
        cancellation = CancellationToken()
        operation_task: asyncio.Future[T] = asyncio.ensure_future(operation(cancellation))
        while True:
            action_task = asyncio.create_task(self.trigger.wait_for_trigger())
            wait_set = {
                cast(asyncio.Future[object], operation_task),
                cast(asyncio.Future[object], action_task),
            }
            await asyncio.wait(
                wait_set,
                return_when=asyncio.FIRST_COMPLETED,
            )
            if operation_task.done():
                if action_task.done():
                    completed_action = await action_task
                    if completed_action != stop_action:
                        self._pending_action = completed_action
                else:
                    action_task.cancel()
                    with suppress(asyncio.CancelledError):
                        await action_task
                return True, await operation_task

            action = await action_task
            if action in {"exit", "cancel"}:
                cancellation.cancel()
                await self._cancel_operation(operation_task)
                return False, None
            if action == "listen_start":
                cancellation.cancel()
                await self._cancel_operation(operation_task)
                self._pending_action = action
                return False, None
            if action == "privacy_toggle":
                cancellation.cancel()
                await self._cancel_operation(operation_task)
                self._pending_action = action
                return False, None
            if action in {"volume_down", "volume_up", "mute_toggle"}:
                await self._handle_output_control(action)
                continue
            if action == stop_action:
                cancellation.request_stop()
                return True, await operation_task

    @staticmethod
    async def _cancel_operation(operation_task: asyncio.Future[T]) -> None:
        try:
            await asyncio.wait_for(asyncio.shield(operation_task), timeout=0.05)
        except (AudioCancelled, asyncio.CancelledError):
            return
        except TimeoutError:
            operation_task.cancel()
            with suppress(asyncio.CancelledError):
                await operation_task


def build_application(
    config: AppConfig,
    *,
    interaction_mode: InteractionMode = "text",
    trigger_override: TriggerDevice | None = None,
    recorder_override: AudioRecorder | None = None,
    latency_observer: Callable[[VoiceLatencySample], None] | None = None,
) -> DeskPetApplication:
    if config.trigger.driver not in {"keyboard", "bluetooth_keyboard"}:
        raise ConfigError(f"Unsupported Stage 1 trigger driver: {config.trigger.driver}")
    if config.face.driver not in {"terminal", "desktop_preview"}:
        raise ConfigError(f"Unsupported desktop face driver: {config.face.driver}")
    if config.agent.provider != "openai":
        raise ConfigError(f"Unsupported model provider: {config.agent.provider}")
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key or api_key == "your-api-key-here":
        raise ConfigError("OPENAI_API_KEY is missing. Copy .env.example to .env and add your key.")

    try:
        runtime_context = load_runtime_context(
            persona_path=config.context.persona_path,
            user_profile_path=config.context.user_profile_path,
            maximum_characters=config.context.maximum_characters,
        )
    except ContextDocumentError as exc:
        raise ConfigError(str(exc)) from exc
    instructions = DESK_PET_INSTRUCTIONS + build_context_instructions(runtime_context)
    realtime_instructions = DESK_PET_INSTRUCTIONS + build_realtime_context_instructions(
        runtime_context
    )
    openai_sdk = AsyncOpenAI(timeout=config.agent.request_timeout_seconds, max_retries=1)

    connector_tools = connector_tools_from_environment()
    connector_loader: OAuthConnectorLoader | None = None
    try:
        connector_loader = OAuthConnectorLoader(
            OAuthManager(credential_store_from_environment(), UrllibOAuthHTTPClient())
        )
    except CredentialStoreError:
        LOGGER.warning("Secure OAuth account storage is unavailable")
    if connector_tools:
        LOGGER.info(
            "Enabled read-only connectors: %s",
            ", ".join(tool["server_label"] for tool in connector_tools),
        )
    response_model = OpenAIModelClient(
        model=config.agent.model,
        reasoning_effort=config.agent.reasoning_effort,
        request_timeout_seconds=config.agent.request_timeout_seconds,
        maximum_output_tokens=config.agent.maximum_output_tokens,
        web_search_enabled=config.agent.web_search_enabled,
        web_search_context_size=config.agent.web_search_context_size,
        connector_tools=connector_tools,
        connector_loader=connector_loader,
        instructions=instructions,
        sdk=openai_sdk,
    )
    events = EventBus()

    async def on_tool_requested(name: str) -> None:
        await events.emit(Event.create(EventType.TOOL_REQUESTED, name=name))

    if config.camera.driver != "opencv":
        raise ConfigError(f"Unsupported camera driver: {config.camera.driver}")
    camera = OpenCVCameraDevice(
        index=config.camera.index,
        maximum_dimension=config.camera.maximum_dimension,
        jpeg_quality=config.camera.jpeg_quality,
    )
    skills = create_default_skill_registry(
        camera=camera,
        image_detail=config.camera.image_detail,
        outlook=WindowsOutlookClassicService() if outlook_classic_installed() else None,
    )
    model = AgentLoop(
        model=response_model,
        skills=skills,
        maximum_tool_iterations=config.agent.maximum_tool_iterations,
        on_tool_requested=on_tool_requested,
    )
    store = ConversationStore(config.storage.database_path)
    conversation = ConversationService(
        model=model,
        store=store,
        history_limit=config.agent.history_limit,
        request_timeout_seconds=config.agent.request_timeout_seconds,
    )
    recorder: AudioRecorder | None = None
    transcriber: TranscriptionService | None = None
    synthesizer: SpeechSynthesizer | None = None
    player: AudioPlayer | None = None
    thinking_audio: ThinkingAudio | None = None
    realtime_voice: OpenAIRealtimeVoice | None = None
    if interaction_mode == "voice":
        supported_audio_drivers = {"system_default", "alsa"}
        if config.audio.input_driver not in supported_audio_drivers:
            raise ConfigError(f"Unsupported audio input driver: {config.audio.input_driver}")
        if config.audio.output_driver not in supported_audio_drivers:
            raise ConfigError(f"Unsupported audio output driver: {config.audio.output_driver}")
        recorder = SoundDeviceRecorder(
            sample_rate_hz=config.audio.sample_rate_hz,
            block_duration_ms=config.audio.block_duration_ms,
            silence_timeout_ms=config.audio.silence_timeout_ms,
            maximum_recording_seconds=config.audio.maximum_recording_seconds,
            silence_threshold=config.audio.silence_threshold,
            device=config.audio.input_device,
            channels=config.audio.input_channels,
        )
        transcriber = OpenAITranscriptionService(
            model=config.audio.transcription_model,
            request_timeout_seconds=config.agent.request_timeout_seconds,
            sdk=openai_sdk,
        )
        synthesizer = OpenAISpeechSynthesizer(
            model=config.audio.speech_model,
            voice=config.audio.voice,
            speed=config.audio.speech_speed,
            request_timeout_seconds=config.agent.request_timeout_seconds,
            sdk=openai_sdk,
        )
        player = SoundDevicePlayer(
            device=config.audio.output_device,
            volume=config.audio.output_volume,
            output_sample_rate_hz=config.audio.output_sample_rate_hz,
            output_channels=config.audio.output_channels,
        )
        realtime_enabled = os.getenv("OPENAI_REALTIME_ENABLED", "true").strip().lower() not in {
            "0",
            "false",
            "no",
            "off",
        }
        if realtime_enabled:
            realtime_voice = OpenAIRealtimeVoice(
                openai_sdk,
                player,
                model=os.getenv("OPENAI_REALTIME_MODEL", "gpt-realtime-2.1-mini"),
                voice=config.audio.voice,
                speed=config.audio.speech_speed,
                instructions=realtime_instructions,
                prewarm=os.getenv("OPENAI_REALTIME_PREWARM", "true").strip().lower()
                not in {"0", "false", "no", "off"},
                skills=skills,
                on_tool_requested=on_tool_requested,
                maximum_tool_iterations=config.agent.maximum_tool_iterations,
            )
        if config.audio.thinking_audio_enabled:
            thinking_audio = ThinkingAudioController(
                player=player,
                volume=config.audio.thinking_volume,
                clip_seconds=config.audio.thinking_clip_seconds,
            )
    input_enabled: Callable[[], bool] | None = None
    if config.face.driver == "desktop_preview":
        preview_face = DesktopPreviewFace()
        face: FaceDevice = preview_face
        input_enabled = preview_face.is_focused
    else:
        face = TerminalFace()
    if config.trigger.driver == "bluetooth_keyboard":
        if sys.platform != "linux":
            raise ConfigError("The Bluetooth keyboard trigger requires Linux")
        if config.trigger.device_name is None:
            raise ConfigError("trigger.device_name is required for bluetooth_keyboard")
        key_reader = EvdevKeyStateReader(device_name=config.trigger.device_name)
    else:
        key_reader = None
    latency_tracker = VoiceLatencyTracker()
    return DeskPetApplication(
        trigger_override
        or KeyboardTrigger(
            key_reader=key_reader,
            listen_key=config.trigger.listen_key,
            cancel_key=config.trigger.cancel_key,
            extra_cancel_keys=("escape",) if config.trigger.cancel_key != "escape" else (),
            enabled_reader=input_enabled,
        ),
        face,
        conversation=conversation,
        events=events,
        interaction_mode=interaction_mode,
        recorder=recorder_override or recorder,
        transcriber=transcriber,
        synthesizer=synthesizer,
        player=player,
        thinking_audio=thinking_audio,
        output_control=player if isinstance(player, SoundDevicePlayer) else None,
        latency_observer=latency_observer or latency_tracker.observe,
        exit_on_idle_cancel=False,
        realtime_voice=realtime_voice,
    )


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Portable AI desk pet")
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("configs/windows.yaml"),
        help="Path to a YAML configuration file",
    )
    parser.add_argument(
        "--mode",
        choices=("text", "voice"),
        default="text",
        help="Use typed input or the laptop microphone and speakers",
    )
    return parser.parse_args(argv)


async def async_main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        load_dotenv()
        config = load_config(args.config)
        mode: InteractionMode = args.mode
        app = build_application(config, interaction_mode=mode)
        print(f"DeskBob ({config.profile}, {config.agent.model}, {mode})")
        listen_key_label = config.trigger.listen_key.replace("_", " ").title()
        if mode == "voice":
            print(
                f"Hold {listen_key_label} to talk; B briefs or sees; C cancels or sleeps; "
                "turn the dial for volume and press it to mute. Press Ctrl+C to exit."
            )
        else:
            print(
                f"Tap {listen_key_label}, type a message, and press Enter. "
                "Press Ctrl+C or close this window to exit."
            )
        await app.run()
        print("Desk Pet stopped cleanly.")
        return 0
    except (ConfigError, RuntimeError) as exc:
        LOGGER.error("%s", exc)
        return 2


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    raise SystemExit(asyncio.run(async_main()))


if __name__ == "__main__":
    main()
