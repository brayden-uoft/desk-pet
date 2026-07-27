from typing import Protocol


class TriggerDevice(Protocol):
    async def wait_for_trigger(self) -> str:
        """Return the triggered action name."""


class FaceDevice(Protocol):
    async def set_state(self, state: str) -> None:
        """Display the state or its animation."""


class AudioRecorder(Protocol):
    async def record_utterance(self) -> bytes:
        """Return a WAV recording."""


class AudioPlayer(Protocol):
    async def play(self, audio: bytes) -> None:
        """Play encoded or PCM audio."""


class CameraDevice(Protocol):
    async def capture_jpeg(self) -> bytes:
        """Capture one JPEG image."""
