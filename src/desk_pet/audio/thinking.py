from __future__ import annotations

import asyncio
from contextlib import suppress
from typing import Protocol

from desk_pet.audio.errors import AudioCancelled
from desk_pet.hardware.interfaces import AudioPlayer, CancellationToken, SpeechSynthesizer


class ThinkingAudio(Protocol):
    async def prepare(self) -> None:
        """Prepare reusable filler audio before the first interaction."""

    async def start(self) -> None:
        """Begin filler playback without waiting for it to finish."""

    async def stop(self) -> None:
        """Stop filler playback before the final answer starts."""


class ThinkingAudioController:
    """Preload and loop a short filler phrase while real work continues."""

    def __init__(
        self,
        *,
        synthesizer: SpeechSynthesizer,
        player: AudioPlayer,
        phrase: str,
    ) -> None:
        self._synthesizer = synthesizer
        self._player = player
        self._phrase = phrase
        self._audio: bytes | None = None
        self._cancellation: CancellationToken | None = None
        self._play_task: asyncio.Task[None] | None = None

    async def prepare(self) -> None:
        self._audio = await self._synthesizer.synthesize(self._phrase)

    async def start(self) -> None:
        if self._audio is None or self._play_task is not None:
            return
        self._cancellation = CancellationToken()
        self._play_task = asyncio.create_task(self._play_loop(self._cancellation))
        await asyncio.sleep(0)

    async def stop(self) -> None:
        if self._play_task is None or self._cancellation is None:
            return
        self._cancellation.cancel()
        with suppress(AudioCancelled):
            await self._play_task
        self._play_task = None
        self._cancellation = None

    async def _play_loop(self, cancellation: CancellationToken) -> None:
        assert self._audio is not None
        while not cancellation.cancelled:
            await self._player.play(self._audio, cancellation)
