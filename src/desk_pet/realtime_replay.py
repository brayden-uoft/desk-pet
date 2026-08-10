from __future__ import annotations

import argparse
import asyncio
import logging
import os
import statistics
import time
from collections.abc import AsyncIterator, Callable, Sequence
from pathlib import Path

from dotenv import load_dotenv
from openai import AsyncOpenAI

from desk_pet.audio.realtime import OpenAIRealtimeVoice, wav_to_realtime_pcm
from desk_pet.config import AppConfig, load_config
from desk_pet.hardware.desktop.sounddevice_audio import SoundDevicePlayer
from desk_pet.hardware.interfaces import CancellationToken, StreamingAudioPlayer
from desk_pet.voice_replay import DEFAULT_FIXTURE

LOGGER = logging.getLogger(__name__)


class RealtimeReplaySession:
    """Keep one speech-to-speech session warm across deterministic replay turns."""

    def __init__(
        self,
        client: AsyncOpenAI,
        player: StreamingAudioPlayer,
        *,
        model: str,
        voice: str,
        speed: float,
        prewarm: bool,
    ) -> None:
        self._voice = OpenAIRealtimeVoice(
            client,
            player,
            model=model,
            voice=voice,
            speed=speed,
            instructions=(
                "You are DeskBob, Brayden's concise, fast, chirpy robotic desk pet. "
                "Answer directly and keep simple replies to one short sentence."
            ),
            prewarm=prewarm,
        )

    async def run(self, recording: bytes, turns: int) -> list[float]:
        latencies: list[float] = []
        await self._voice.start()
        try:
            for index in range(1, turns + 1):
                print(f"Realtime replay turn {index}/{turns}")
                await self._voice.begin_audio_input()
                pcm = wav_to_realtime_pcm(recording)
                for offset in range(0, len(pcm), 1_440):
                    await self._voice.append_audio_input(pcm[offset : offset + 1_440])
                started = time.perf_counter()
                first_audio = 0.0

                def audio_started() -> None:
                    nonlocal first_audio
                    first_audio = time.perf_counter()

                result = await self._voice.respond_to_streamed_audio(
                    CancellationToken(),
                    audio_started,
                )
                if result.delegated_request is not None:
                    raise RuntimeError(
                        f"Fixture unexpectedly delegated: {result.delegated_request}"
                    )
                if not first_audio:
                    raise RuntimeError("Realtime response completed without audio")
                latency_ms = (first_audio - started) * 1000
                latencies.append(latency_ms)
                print(f"You> {result.user_transcript}")
                print(f"DeskBob> {result.assistant_transcript}")
                print(f"INFO: Realtime release-to-first-audio={latency_ms:.0f}ms")
        finally:
            await self._voice.close()
        return latencies


class DiscardingAudioPlayer:
    """Consume live audio without a sound device while preserving first-byte timing."""

    async def play_pcm_stream(
        self,
        chunks: AsyncIterator[bytes],
        cancellation: CancellationToken,
        on_audio_started: Callable[[], None],
    ) -> None:
        started = False
        async for _chunk in chunks:
            if cancellation.cancelled:
                return
            if not started:
                started = True
                on_audio_started()


def _player(config: AppConfig) -> SoundDevicePlayer:
    return SoundDevicePlayer(
        device=config.audio.output_device,
        block_duration_ms=config.audio.block_duration_ms,
        volume=config.audio.output_volume,
        output_sample_rate_hz=config.audio.output_sample_rate_hz,
        output_channels=config.audio.output_channels,
    )


def _summary(samples: list[float]) -> str:
    ordered = sorted(samples)
    p50 = statistics.median(ordered)
    p95_index = max(0, min(len(ordered) - 1, round(0.95 * len(ordered) + 0.5) - 1))
    return (
        f"Realtime latency summary ({len(samples)} turns): "
        f"release-to-first-audio p50={p50:.0f}ms "
        f"p95={ordered[p95_index]:.0f}ms best={ordered[0]:.0f}ms"
    )


async def async_main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Benchmark DeskBob's Realtime voice lane")
    parser.add_argument("--config", type=Path, default=Path("configs/windows.yaml"))
    parser.add_argument("--audio", type=Path, default=DEFAULT_FIXTURE)
    parser.add_argument("--turns", type=int, default=5)
    parser.add_argument("--no-playback", action="store_true")
    args = parser.parse_args(argv)
    if args.turns < 1:
        parser.error("--turns must be at least one")
    load_dotenv()
    config = load_config(args.config)
    recording = args.audio.read_bytes()
    model = os.getenv("OPENAI_REALTIME_MODEL", "gpt-realtime-2.1-mini")
    session = RealtimeReplaySession(
        AsyncOpenAI(),
        DiscardingAudioPlayer() if args.no_playback else _player(config),
        model=model,
        voice=config.audio.voice,
        speed=config.audio.speech_speed,
        prewarm=os.getenv("OPENAI_REALTIME_PREWARM", "true").strip().lower()
        not in {"0", "false", "no", "off"},
    )
    samples = await session.run(recording, args.turns)
    LOGGER.info(_summary(samples))
    return 0


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    raise SystemExit(asyncio.run(async_main()))


if __name__ == "__main__":
    main()
