from __future__ import annotations

import argparse
import asyncio
import logging
import os
from collections.abc import Awaitable, Callable, Sequence
from contextlib import suppress
from functools import partial
from pathlib import Path
from typing import Literal, TypeVar, cast

from dotenv import load_dotenv

from desk_pet.agent.client import OpenAIModelClient
from desk_pet.agent.connectors import OAuthConnectorLoader, connector_tools_from_environment
from desk_pet.agent.loop import AgentLoop
from desk_pet.agent.prompts import DESK_PET_INSTRUCTIONS
from desk_pet.audio.errors import AudioCancelled, AudioError
from desk_pet.audio.openai_services import OpenAISpeechSynthesizer, OpenAITranscriptionService
from desk_pet.audio.speech_text import text_for_speech
from desk_pet.audio.thinking import ThinkingAudio, ThinkingAudioController
from desk_pet.auth.http import UrllibOAuthHTTPClient
from desk_pet.auth.oauth import OAuthManager
from desk_pet.auth.store import CredentialStoreError, KeyringCredentialStore
from desk_pet.config import AppConfig, ConfigError, load_config
from desk_pet.conversation import ConversationError, ConversationService
from desk_pet.events import Event, EventBus, EventType
from desk_pet.hardware.desktop.keyboard_trigger import KeyboardTrigger
from desk_pet.hardware.desktop.opencv_camera import OpenCVCameraDevice
from desk_pet.hardware.desktop.preview_face import DesktopPreviewFace
from desk_pet.hardware.desktop.simulated_face import TerminalFace
from desk_pet.hardware.desktop.sounddevice_audio import SoundDevicePlayer, SoundDeviceRecorder
from desk_pet.hardware.interfaces import (
    AudioPlayer,
    AudioRecorder,
    CancellationToken,
    FaceDevice,
    SpeechSynthesizer,
    TranscriptionService,
    TriggerDevice,
)
from desk_pet.memory.context import (
    ContextDocumentError,
    build_context_instructions,
    load_runtime_context,
)
from desk_pet.memory.conversation_store import ConversationStore
from desk_pet.skills.defaults import create_default_skill_registry
from desk_pet.state_machine import PetState, StateMachine

LOGGER = logging.getLogger(__name__)
InteractionMode = Literal["text", "voice"]
T = TypeVar("T")


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
        exit_on_idle_cancel: bool = True,
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
        self.exit_on_idle_cancel = exit_on_idle_cancel
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
            if self.thinking_audio is not None:
                try:
                    await self.thinking_audio.prepare()
                except AudioError:
                    LOGGER.warning("Thinking filler audio could not be prepared")
            await self.state.transition_to(PetState.IDLE)
            while True:
                action = await self.trigger.wait_for_trigger()
                await self.events.emit(Event.create(EventType.TRIGGER_RECEIVED, action=action))
                if action == "shutdown" or (action == "exit" and self.exit_on_idle_cancel):
                    return
                if action in {"listen", "listen_start"}:
                    await self._handle_listen()
        finally:
            await self.face.close()

    async def _handle_listen(self) -> None:
        await self.state.transition_to(PetState.LISTENING)
        if self.interaction_mode == "voice" and self.thinking_audio is not None:
            await self.thinking_audio.listen_started()
        if self.conversation is None:
            await asyncio.sleep(0.35)
            await self.state.transition_to(PetState.IDLE)
            return

        user_text = await self._collect_user_text()
        if user_text is None:
            await self._stop_thinking_audio()
            await self.state.transition_to(PetState.IDLE)
            return
        if not user_text:
            if self.interaction_mode == "voice":
                self.output("I didn't hear a question. Hold the push-to-talk key while speaking.")
            else:
                self.output("Type a message after pressing the input key.")
            await self._stop_thinking_audio()
            await self.state.transition_to(PetState.IDLE)
            return

        await self.events.emit(Event.create(EventType.TRANSCRIPT_READY, text=user_text))
        await self.state.transition_to(PetState.THINKING)
        try:
            assistant_text = await self.conversation.reply(user_text)
        except ConversationError as exc:
            await self._stop_thinking_audio()
            await self.state.transition_to(PetState.ERROR)
            self.output(f"DeskBob> {exc}")
            await self.state.transition_to(PetState.IDLE)
            return

        await self.events.emit(Event.create(EventType.RESPONSE_READY, text=assistant_text))
        if self.interaction_mode == "voice":
            assert self.synthesizer is not None
            assert self.player is not None
            try:
                spoken_text = text_for_speech(assistant_text)
                if not spoken_text:
                    spoken_text = "I put the link in the text window."
                speech = await self.synthesizer.synthesize(spoken_text)
                await self._stop_thinking_audio()
                await self.state.transition_to(PetState.SPEAKING)
                self.output(f"DeskBob> {assistant_text}")
                await self._run_cancellable(partial(self.player.play, speech))
            except AudioError as exc:
                await self._stop_thinking_audio()
                await self.state.transition_to(PetState.ERROR)
                self.output(f"DeskBob audio error> {exc}")
        else:
            await self.state.transition_to(PetState.SPEAKING)
            self.output(f"DeskBob> {assistant_text}")
        await self.state.transition_to(PetState.IDLE)

    async def _collect_user_text(self) -> str | None:
        if self.interaction_mode == "text":
            return (await asyncio.to_thread(self.text_input, "You> ")).strip()

        assert self.recorder is not None
        assert self.transcriber is not None
        try:
            completed, recording = await self._run_cancellable(
                self.recorder.record_utterance,
                stop_action="listen_stop",
            )
            if not completed or recording is None:
                return None
            if self.thinking_audio is not None:
                await self.thinking_audio.start()
            await self.state.transition_to(PetState.TRANSCRIBING)
            transcript = (await self.transcriber.transcribe(recording)).strip()
            if transcript:
                self.output(f"You> {transcript}")
            return transcript
        except AudioError as exc:
            await self.state.transition_to(PetState.ERROR)
            self.output(f"DeskBob audio error> {exc}")
            return None

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
                action_task.cancel()
                with suppress(asyncio.CancelledError):
                    await action_task
                return True, await operation_task

            action = await action_task
            if action == "exit":
                cancellation.cancel()
                with suppress(AudioCancelled):
                    await operation_task
                return False, None
            if action == stop_action:
                cancellation.request_stop()
                return True, await operation_task


def build_application(
    config: AppConfig,
    *,
    interaction_mode: InteractionMode = "text",
) -> DeskPetApplication:
    if config.trigger.driver != "keyboard":
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

    connector_tools = connector_tools_from_environment()
    connector_loader: OAuthConnectorLoader | None = None
    try:
        connector_loader = OAuthConnectorLoader(
            OAuthManager(KeyringCredentialStore(), UrllibOAuthHTTPClient())
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
    model = AgentLoop(
        model=response_model,
        skills=create_default_skill_registry(
            camera=camera,
            image_detail=config.camera.image_detail,
        ),
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
    if interaction_mode == "voice":
        if config.profile != "windows":
            raise ConfigError("Stage 4 voice mode currently supports the Windows profile")
        if config.audio.input_driver != "system_default":
            raise ConfigError(
                f"Unsupported Windows audio input driver: {config.audio.input_driver}"
            )
        if config.audio.output_driver != "system_default":
            raise ConfigError(
                f"Unsupported Windows audio output driver: {config.audio.output_driver}"
            )
        recorder = SoundDeviceRecorder(
            sample_rate_hz=config.audio.sample_rate_hz,
            block_duration_ms=config.audio.block_duration_ms,
            silence_timeout_ms=config.audio.silence_timeout_ms,
            maximum_recording_seconds=config.audio.maximum_recording_seconds,
            silence_threshold=config.audio.silence_threshold,
            device=config.audio.input_device,
        )
        transcriber = OpenAITranscriptionService(
            model=config.audio.transcription_model,
            request_timeout_seconds=config.agent.request_timeout_seconds,
        )
        synthesizer = OpenAISpeechSynthesizer(
            model=config.audio.speech_model,
            voice=config.audio.voice,
            speed=config.audio.speech_speed,
            request_timeout_seconds=config.agent.request_timeout_seconds,
        )
        player = SoundDevicePlayer(device=config.audio.output_device)
        if config.audio.thinking_audio_enabled:
            thinking_audio = ThinkingAudioController(
                player=player,
                volume=config.audio.thinking_volume,
                clip_seconds=config.audio.thinking_clip_seconds,
            )
    face: FaceDevice = (
        DesktopPreviewFace() if config.face.driver == "desktop_preview" else TerminalFace()
    )
    return DeskPetApplication(
        KeyboardTrigger(
            listen_key=config.trigger.listen_key,
            cancel_key=config.trigger.cancel_key,
        ),
        face,
        conversation=conversation,
        events=events,
        interaction_mode=interaction_mode,
        recorder=recorder,
        transcriber=transcriber,
        synthesizer=synthesizer,
        player=player,
        thinking_audio=thinking_audio,
        exit_on_idle_cancel=False,
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
                f"Hold {listen_key_label} while speaking, then release it to send. "
                "Escape cancels active audio. Press Ctrl+C or close this window to exit."
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
