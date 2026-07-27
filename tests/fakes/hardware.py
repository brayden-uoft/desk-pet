from __future__ import annotations

import asyncio
from collections.abc import Iterable

from desk_pet.audio.errors import AudioCancelled
from desk_pet.hardware.interfaces import CancellationToken


class FakeTrigger:
    def __init__(self, actions: Iterable[str]) -> None:
        self._actions = iter(actions)

    async def wait_for_trigger(self) -> str:
        return next(self._actions)


class FakeFace:
    def __init__(self) -> None:
        self.states: list[str] = []

    async def set_state(self, state: str) -> None:
        self.states.append(state)


class QueueTrigger:
    def __init__(self) -> None:
        self._actions: asyncio.Queue[str] = asyncio.Queue()

    async def send(self, action: str) -> None:
        await self._actions.put(action)

    async def wait_for_trigger(self) -> str:
        return await self._actions.get()


class FakeRecorder:
    def __init__(self, audio: bytes = b"fake-wav") -> None:
        self.audio = audio
        self.calls = 0

    async def record_utterance(self, cancellation: CancellationToken) -> bytes:
        self.calls += 1
        await asyncio.sleep(0)
        if cancellation.cancelled:
            raise AudioCancelled("Recording cancelled.")
        return self.audio


class CancellableRecorder:
    def __init__(self) -> None:
        self.started = asyncio.Event()

    async def record_utterance(self, cancellation: CancellationToken) -> bytes:
        self.started.set()
        while not cancellation.cancelled:
            await asyncio.sleep(0)
        raise AudioCancelled("Recording cancelled.")


class FakeTranscriber:
    def __init__(self, transcript: str) -> None:
        self.transcript = transcript
        self.recordings: list[bytes] = []

    async def transcribe(self, audio: bytes) -> str:
        self.recordings.append(audio)
        return self.transcript


class FakeSynthesizer:
    def __init__(self, audio: bytes = b"fake-speech-wav") -> None:
        self.audio = audio
        self.texts: list[str] = []

    async def synthesize(self, text: str) -> bytes:
        self.texts.append(text)
        return self.audio


class FakePlayer:
    def __init__(self) -> None:
        self.audio: list[bytes] = []

    async def play(self, audio: bytes, cancellation: CancellationToken) -> None:
        self.audio.append(audio)
        await asyncio.sleep(0)
        if cancellation.cancelled:
            raise AudioCancelled("Playback cancelled.")


class CancellablePlayer:
    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.cancelled = False

    async def play(self, audio: bytes, cancellation: CancellationToken) -> None:
        self.started.set()
        while not cancellation.cancelled:
            await asyncio.sleep(0)
        self.cancelled = True
        raise AudioCancelled("Playback cancelled.")


class FakeCamera:
    def __init__(self, jpeg: bytes = b"\xff\xd8fake-jpeg\xff\xd9") -> None:
        self.jpeg = jpeg
        self.calls = 0

    async def capture_jpeg(self) -> bytes:
        self.calls += 1
        return self.jpeg
