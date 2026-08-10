from __future__ import annotations

import threading
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Protocol, runtime_checkable


class CancellationToken:
    """Thread-safe stop and cancellation signals for blocking device adapters."""

    def __init__(self) -> None:
        self._event = threading.Event()
        self._stop_event = threading.Event()

    def cancel(self) -> None:
        self._event.set()

    def request_stop(self) -> None:
        self._stop_event.set()

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()

    @property
    def stop_requested(self) -> bool:
        return self._stop_event.is_set()


class TriggerDevice(Protocol):
    async def wait_for_trigger(self) -> str:
        """Return the triggered action name."""


class FaceDevice(Protocol):
    async def set_state(self, state: str) -> None:
        """Display the state or its animation."""

    async def close(self) -> None:
        """Release display resources."""


class AudioRecorder(Protocol):
    async def record_utterance(self, cancellation: CancellationToken) -> bytes:
        """Return a WAV recording."""


@runtime_checkable
class StreamingAudioRecorder(Protocol):
    async def record_utterance_stream(
        self,
        cancellation: CancellationToken,
        on_pcm_chunk: Callable[[bytes], Awaitable[None]],
    ) -> bytes:
        """Return WAV audio while emitting 24 kHz mono PCM chunks."""


class AudioPlayer(Protocol):
    async def play(self, audio: bytes, cancellation: CancellationToken) -> None:
        """Play encoded or PCM audio."""


@runtime_checkable
class ManagedAudioPlayer(Protocol):
    async def prepare(self) -> None:
        """Open and warm the output device."""

    async def close(self) -> None:
        """Release the output device."""


@runtime_checkable
class StreamingAudioPlayer(Protocol):
    async def play_pcm_stream(
        self,
        chunks: AsyncIterator[bytes],
        cancellation: CancellationToken,
        on_audio_started: Callable[[], None],
    ) -> None:
        """Play 24 kHz mono signed 16-bit PCM chunks as they arrive."""


class AudioOutputControl(Protocol):
    @property
    def volume(self) -> float:
        """Return output gain from zero to one."""

    @property
    def muted(self) -> bool:
        """Return whether output is muted."""

    def set_volume(self, volume: float) -> None:
        """Set output gain from zero to one."""

    def set_muted(self, muted: bool) -> None:
        """Mute or unmute output."""


class CameraDevice(Protocol):
    async def capture_jpeg(self) -> bytes:
        """Capture one JPEG image."""


class TranscriptionService(Protocol):
    async def transcribe(self, audio: bytes) -> str:
        """Convert a WAV recording to text."""


class SpeechSynthesizer(Protocol):
    async def synthesize(self, text: str) -> bytes:
        """Convert text to WAV audio."""


@runtime_checkable
class StreamingSpeechSynthesizer(Protocol):
    def synthesize_pcm_stream(self, text: str) -> AsyncIterator[bytes]:
        """Yield 24 kHz mono signed 16-bit PCM speech chunks."""
