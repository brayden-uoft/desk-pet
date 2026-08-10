from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import suppress
from dataclasses import dataclass
from time import perf_counter
from typing import Any, Protocol, runtime_checkable

from openai import AsyncOpenAI

from desk_pet.audio.wav import decode_wav
from desk_pet.hardware.desktop.sounddevice_audio import _resample_pcm16
from desk_pet.hardware.interfaces import CancellationToken, StreamingAudioPlayer
from desk_pet.skills.registry import SkillError, SkillRegistry

LOGGER = logging.getLogger(__name__)
_END = object()


@dataclass(frozen=True, slots=True)
class RealtimeVoiceResult:
    user_transcript: str
    assistant_transcript: str
    delegated_request: str | None = None
    timing: RealtimeVoiceTiming | None = None


@dataclass(frozen=True, slots=True)
class RealtimeVoiceTiming:
    prepare_and_commit_seconds: float
    commit_to_server_audio_seconds: float
    server_audio_to_speaker_seconds: float
    total_response_seconds: float
    tool_seconds: float = 0.0


class RealtimeVoiceService(Protocol):
    async def start(self) -> None: ...

    async def close(self) -> None: ...

    async def respond(
        self,
        recording: bytes,
        cancellation: CancellationToken,
        on_audio_started: Callable[[], None],
    ) -> RealtimeVoiceResult: ...


@runtime_checkable
class StreamingRealtimeVoiceService(Protocol):
    async def begin_audio_input(self) -> None: ...

    async def append_audio_input(self, pcm_24khz: bytes) -> None: ...

    async def cancel_audio_input(self) -> None: ...

    async def respond_to_streamed_audio(
        self,
        cancellation: CancellationToken,
        on_audio_started: Callable[[], None],
    ) -> RealtimeVoiceResult: ...


def wav_to_realtime_pcm(audio: bytes) -> bytes:
    """Convert a mono 16-bit WAV recording to 24 kHz PCM."""
    sample_rate, channels, sample_width, frames = decode_wav(audio)
    if sample_width != 2:
        raise ValueError("Realtime voice requires 16-bit WAV audio")
    if channels != 1:
        raise ValueError("Realtime voice requires mono WAV audio")
    return _resample_pcm16(frames, channels, sample_rate, 24_000)


class OpenAIRealtimeVoice:
    """Persistent low-latency voice session with safe delegation to the full agent."""

    def __init__(
        self,
        client: AsyncOpenAI,
        player: StreamingAudioPlayer,
        *,
        model: str,
        voice: str,
        speed: float,
        instructions: str,
        prewarm: bool = True,
        skills: SkillRegistry | None = None,
        on_tool_requested: Callable[[str], Awaitable[None]] | None = None,
        maximum_tool_iterations: int = 5,
    ) -> None:
        self._client = client
        self._player = player
        self._model = model
        self._voice = voice
        self._speed = min(1.5, speed)
        self._instructions = instructions
        self._prewarm_enabled = prewarm
        self._skills = skills
        self._on_tool_requested = on_tool_requested
        self._maximum_tool_iterations = maximum_tool_iterations
        self._manager: Any = None
        self._connection: Any = None
        self._streamed_input_started_at: float | None = None

    async def start(self) -> None:
        if self._connection is not None:
            return
        self._manager = self._client.realtime.connect(model=self._model)
        self._connection = await self._manager.__aenter__()
        try:
            await self._connection.session.update(session=self._session_config())
            await self._wait_for_session()
            if self._prewarm_enabled:
                await self._prewarm()
        except BaseException:
            await self.close()
            raise

    async def close(self) -> None:
        if self._manager is not None:
            manager, self._manager = self._manager, None
            self._connection = None
            await manager.__aexit__(None, None, None)

    async def respond(
        self,
        recording: bytes,
        cancellation: CancellationToken,
        on_audio_started: Callable[[], None],
    ) -> RealtimeVoiceResult:
        turn_started_at = perf_counter()
        await self.start()
        connection = self._connection
        assert connection is not None
        pcm = wav_to_realtime_pcm(recording)
        await connection.input_audio_buffer.append(audio=base64.b64encode(pcm).decode("ascii"))
        await connection.input_audio_buffer.commit()
        committed_at = perf_counter()
        await connection.response.create()
        try:
            return await self._consume_response(
                connection,
                cancellation,
                on_audio_started,
                turn_started_at=turn_started_at,
                committed_at=committed_at,
            )
        except asyncio.CancelledError:
            with suppress(Exception):
                await connection.response.cancel()
                await connection.input_audio_buffer.clear()
            raise

    async def begin_audio_input(self) -> None:
        await self.start()
        self._streamed_input_started_at = perf_counter()

    async def append_audio_input(self, pcm_24khz: bytes) -> None:
        connection = self._connection
        if connection is None or self._streamed_input_started_at is None:
            raise RuntimeError("Realtime audio input was not started")
        await connection.input_audio_buffer.append(
            audio=base64.b64encode(pcm_24khz).decode("ascii")
        )

    async def cancel_audio_input(self) -> None:
        if self._connection is not None and self._streamed_input_started_at is not None:
            await self._connection.input_audio_buffer.clear()
        self._streamed_input_started_at = None

    async def respond_to_streamed_audio(
        self,
        cancellation: CancellationToken,
        on_audio_started: Callable[[], None],
    ) -> RealtimeVoiceResult:
        connection = self._connection
        turn_started_at, self._streamed_input_started_at = (
            self._streamed_input_started_at,
            None,
        )
        if connection is None or turn_started_at is None:
            raise RuntimeError("Realtime audio input was not started")
        await connection.input_audio_buffer.commit()
        committed_at = perf_counter()
        await connection.response.create()
        return await self._consume_response(
            connection,
            cancellation,
            on_audio_started,
            turn_started_at=turn_started_at,
            committed_at=committed_at,
        )

    def _session_config(self) -> dict[str, Any]:
        delegation = {
            "type": "function",
            "name": "delegate_to_full_agent",
            "description": (
                "Use this instead of answering whenever the request needs live/current facts, "
                "web search, weather, news, calendar, email, files, connected accounts, camera, "
                "timers, durable memory, or any external tool/action. Preserve the user's request."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "request": {
                        "type": "string",
                        "description": "The user's complete request in plain text.",
                    }
                },
                "required": ["request"],
                "additionalProperties": False,
            },
        }
        direct_tools: list[dict[str, Any]] = []
        if self._skills is not None:
            direct_tools = [
                {
                    "type": "function",
                    "name": schema["name"],
                    "description": schema["description"],
                    "parameters": schema["parameters"],
                }
                for schema in self._skills.schemas()
            ]
        return {
            "type": "realtime",
            "model": self._model,
            "output_modalities": ["audio"],
            "instructions": (
                f"{self._instructions}\n\n"
                "VOICE FAST-LANE RULES: Reply directly only for casual conversation, general "
                "knowledge, advice, brainstorming, and follow-ups that need no external data. "
                "For anything listed by delegate_to_full_agent, call that tool immediately and "
                "do not fabricate an answer. Keep direct voice answers concise and speak quickly."
            ),
            "max_output_tokens": 4_096,
            "reasoning": {"effort": "minimal"},
            "tools": [*direct_tools, delegation],
            "tool_choice": "auto",
            "audio": {
                "input": {
                    "format": {"type": "audio/pcm", "rate": 24_000},
                    "turn_detection": None,
                    "transcription": {
                        "model": "gpt-4o-mini-transcribe",
                        "language": "en",
                    },
                },
                "output": {
                    "format": {"type": "audio/pcm", "rate": 24_000},
                    "voice": self._voice,
                    "speed": self._speed,
                },
            },
        }

    async def _wait_for_session(self) -> None:
        async for event in self._connection:
            if event.type == "session.updated":
                return
            if event.type == "error":
                raise RuntimeError(f"Realtime session setup failed: {event.error}")

    async def _prewarm(self) -> None:
        await self._connection.response.create(
            response={
                "conversation": "none",
                "output_modalities": ["text"],
                "input": [
                    {
                        "type": "message",
                        "role": "user",
                        "content": [{"type": "input_text", "text": "Ready?"}],
                    }
                ],
                "max_output_tokens": 1,
                "tools": [],
                "tool_choice": "none",
            }
        )
        while True:
            event = await self._connection.recv()
            if event.type == "response.done":
                return
            if event.type == "error":
                raise RuntimeError(f"Realtime prewarm failed: {event.error}")

    async def _consume_response(
        self,
        connection: Any,
        cancellation: CancellationToken,
        on_audio_started: Callable[[], None],
        *,
        turn_started_at: float,
        committed_at: float,
    ) -> RealtimeVoiceResult:
        queue: asyncio.Queue[bytes | object] = asyncio.Queue()
        assistant_transcript: list[str] = []
        user_transcript = ""
        input_item_id: str | None = None
        delegated_request: str | None = None
        audio_bytes = 0
        audio_chunks = 0
        first_server_audio_at = 0.0
        first_speaker_audio_at = 0.0
        tool_seconds = 0.0
        tool_calls_this_response = False
        tool_iterations = 0
        seen_calls: set[str] = set()

        def speaker_audio_started() -> None:
            nonlocal first_speaker_audio_at
            if not first_speaker_audio_at:
                first_speaker_audio_at = perf_counter()
                on_audio_started()

        async def chunks() -> AsyncIterator[bytes]:
            while True:
                item = await queue.get()
                if item is _END:
                    return
                if isinstance(item, bytes):
                    yield item

        playback = asyncio.create_task(
            self._player.play_pcm_stream(chunks(), cancellation, speaker_audio_started)
        )
        try:
            while True:
                event = await connection.recv()
                if cancellation.cancelled:
                    await connection.response.cancel()
                    break
                if event.type == "response.output_audio.delta":
                    if not first_server_audio_at:
                        first_server_audio_at = perf_counter()
                    chunk = base64.b64decode(event.delta)
                    audio_bytes += len(chunk)
                    audio_chunks += 1
                    await queue.put(chunk)
                elif event.type == "response.output_audio_transcript.delta":
                    assistant_transcript.append(event.delta)
                elif event.type == "input_audio_buffer.committed":
                    input_item_id = event.item_id
                elif event.type == "conversation.item.input_audio_transcription.completed":
                    if input_item_id is not None and event.item_id == input_item_id:
                        user_transcript = event.transcript
                elif event.type == "response.function_call_arguments.done":
                    if event.name == "delegate_to_full_agent":
                        arguments = json.loads(event.arguments)
                        request = arguments.get("request")
                        if isinstance(request, str) and request.strip():
                            delegated_request = request.strip()
                    elif self._skills is not None:
                        tool_iterations += 1
                        if tool_iterations > self._maximum_tool_iterations:
                            raise RuntimeError("Realtime tool loop exceeded its iteration limit")
                        fingerprint = hashlib.sha256(
                            f"{event.name}\0{event.arguments}".encode()
                        ).hexdigest()
                        if fingerprint in seen_calls:
                            output: Any = json.dumps({"ok": False, "error": "duplicate_tool_call"})
                        else:
                            seen_calls.add(fingerprint)
                            if self._on_tool_requested is not None:
                                await self._on_tool_requested(event.name)
                            tool_started = perf_counter()
                            try:
                                output = await self._skills.execute(
                                    event.name,
                                    event.arguments,
                                )
                            except SkillError as exc:
                                output = json.dumps(
                                    {"ok": False, "error": exc.code, "message": str(exc)}
                                )
                            tool_seconds += perf_counter() - tool_started
                        await self._submit_tool_output(connection, event.call_id, output)
                        tool_calls_this_response = True
                elif event.type == "response.done":
                    if event.response.status not in {"completed", "incomplete"}:
                        raise RuntimeError(
                            f"Realtime response ended with status {event.response.status}"
                        )
                    if event.response.status == "incomplete":
                        LOGGER.warning(
                            "Realtime response was incomplete: %s",
                            event.response.status_details,
                        )
                    if tool_calls_this_response and delegated_request is None:
                        tool_calls_this_response = False
                        await connection.response.create()
                        continue
                    break
                elif event.type == "error":
                    raise RuntimeError(f"Realtime response failed: {event.error}")

            # Transcription is intentionally asynchronous and can trail the audio
            # response. Correlate it to this input item so history never shifts by
            # one turn. Waiting here does not delay first audio or playback.
            if not user_transcript and input_item_id is not None:
                try:
                    async with asyncio.timeout(0.75):
                        while not user_transcript:
                            event = await connection.recv()
                            if (
                                event.type
                                == "conversation.item.input_audio_transcription.completed"
                                and event.item_id == input_item_id
                            ):
                                user_transcript = event.transcript
                            elif event.type == "error":
                                raise RuntimeError(f"Realtime transcription failed: {event.error}")
                except TimeoutError:
                    LOGGER.warning("Realtime input transcript was not ready for this turn")
        finally:
            await queue.put(_END)
            await playback
        LOGGER.info(
            "Realtime audio received: chunks=%d bytes=%d duration=%.2fs",
            audio_chunks,
            audio_bytes,
            audio_bytes / (24_000 * 2),
        )
        return RealtimeVoiceResult(
            user_transcript=user_transcript.strip(),
            assistant_transcript="".join(assistant_transcript).strip(),
            delegated_request=delegated_request,
            timing=RealtimeVoiceTiming(
                prepare_and_commit_seconds=committed_at - turn_started_at,
                commit_to_server_audio_seconds=max(0.0, first_server_audio_at - committed_at),
                server_audio_to_speaker_seconds=max(
                    0.0,
                    first_speaker_audio_at - first_server_audio_at,
                ),
                total_response_seconds=perf_counter() - turn_started_at,
                tool_seconds=tool_seconds,
            ),
        )

    @staticmethod
    async def _submit_tool_output(connection: Any, call_id: str, output: Any) -> None:
        images: list[dict[str, Any]] = []
        if isinstance(output, str):
            text_output = output
        else:
            text_parts = [
                item.get("text", "") for item in output if item.get("type") == "input_text"
            ]
            images = [item for item in output if item.get("type") == "input_image"]
            text_output = "\n".join(text_parts) or json.dumps({"ok": True})
        await connection.conversation.item.create(
            item={"type": "function_call_output", "call_id": call_id, "output": text_output}
        )
        if images:
            await connection.conversation.item.create(
                item={
                    "type": "message",
                    "role": "user",
                    "content": [
                        {
                            "type": "input_image",
                            "image_url": item["image_url"],
                            "detail": item.get("detail", "auto"),
                        }
                        for item in images
                    ],
                }
            )
