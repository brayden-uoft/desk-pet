from __future__ import annotations

import threading
from typing import Protocol


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


class AudioPlayer(Protocol):
    async def play(self, audio: bytes, cancellation: CancellationToken) -> None:
        """Play encoded or PCM audio."""


class CameraDevice(Protocol):
    async def capture_jpeg(self) -> bytes:
        """Capture one JPEG image."""


class TranscriptionService(Protocol):
    async def transcribe(self, audio: bytes) -> str:
        """Convert a WAV recording to text."""


class SpeechSynthesizer(Protocol):
    async def synthesize(self, text: str) -> bytes:
        """Convert text to WAV audio."""
