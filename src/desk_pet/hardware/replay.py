from __future__ import annotations

import asyncio

from desk_pet.audio.errors import AudioCancelled
from desk_pet.hardware.interfaces import CancellationToken


class QueuedTrigger:
    """Trigger controlled by a local test or replay harness."""

    def __init__(self) -> None:
        self._actions: asyncio.Queue[str] = asyncio.Queue()

    async def send(self, action: str) -> None:
        await self._actions.put(action)

    async def wait_for_trigger(self) -> str:
        return await self._actions.get()


class ReplayAudioRecorder:
    """Replay private WAV bytes through the normal AudioRecorder interface."""

    def __init__(self, audio: bytes) -> None:
        if not audio:
            raise ValueError("Replay audio must not be empty")
        self._audio = audio
        self._starts: asyncio.Queue[int] = asyncio.Queue()
        self.calls = 0

    async def wait_until_started(self) -> int:
        return await self._starts.get()

    async def record_utterance(self, cancellation: CancellationToken) -> bytes:
        self.calls += 1
        await self._starts.put(self.calls)
        while not cancellation.stop_requested:
            if cancellation.cancelled:
                raise AudioCancelled("Replay recording cancelled.")
            await asyncio.sleep(0)
        return self._audio
