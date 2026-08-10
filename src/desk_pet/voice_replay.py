from __future__ import annotations

import argparse
import asyncio
import logging
from collections.abc import Sequence
from pathlib import Path

from dotenv import load_dotenv

from desk_pet.config import AppConfig, load_config
from desk_pet.hardware.desktop.sounddevice_audio import SoundDeviceRecorder
from desk_pet.hardware.interfaces import CancellationToken
from desk_pet.hardware.replay import QueuedTrigger, ReplayAudioRecorder
from desk_pet.latency import VoiceLatencySample, VoiceLatencyTracker
from desk_pet.main import DeskPetApplication, build_application

DEFAULT_FIXTURE = Path("data/private/voice-fixtures/brayden-latency.wav")


class VoiceReplayController:
    """Drive completed push-to-talk turns without keyboard or microphone input."""

    def __init__(self, audio: bytes, *, summary_interval: int) -> None:
        self.trigger = QueuedTrigger()
        self.recorder = ReplayAudioRecorder(audio)
        self.tracker = VoiceLatencyTracker(summary_interval=summary_interval)
        self._completed: asyncio.Queue[VoiceLatencySample] = asyncio.Queue()

    def observe(self, sample: VoiceLatencySample) -> None:
        self.tracker.observe(sample)
        self._completed.put_nowait(sample)

    async def run(
        self,
        app: DeskPetApplication,
        *,
        turns: int,
        turn_timeout_seconds: float = 60.0,
    ) -> None:
        if turns < 1:
            raise ValueError("turns must be at least one")
        if turn_timeout_seconds <= 0:
            raise ValueError("turn_timeout_seconds must be positive")
        app_task = asyncio.create_task(app.run())
        try:
            for turn in range(1, turns + 1):
                print(f"Replay turn {turn}/{turns}")
                await self.trigger.send("listen_start")
                started_turn = await self.recorder.wait_until_started()
                if started_turn != turn:
                    raise RuntimeError("Replay recorder and controller lost synchronization")
                await self.trigger.send("listen_stop")
                try:
                    await asyncio.wait_for(
                        self._completed.get(),
                        timeout=turn_timeout_seconds,
                    )
                except TimeoutError as exc:
                    raise RuntimeError(
                        f"Replay turn {turn} did not complete within "
                        f"{turn_timeout_seconds:g} seconds"
                    ) from exc
        finally:
            await self.trigger.send("shutdown")
            await app_task


def _recorder(config: AppConfig) -> SoundDeviceRecorder:
    return SoundDeviceRecorder(
        sample_rate_hz=config.audio.sample_rate_hz,
        block_duration_ms=config.audio.block_duration_ms,
        silence_timeout_ms=config.audio.silence_timeout_ms,
        maximum_recording_seconds=config.audio.maximum_recording_seconds,
        silence_threshold=config.audio.silence_threshold,
        device=config.audio.input_device,
        channels=config.audio.input_channels,
    )


async def record_fixture(config: AppConfig, output_path: Path, prompt: str) -> None:
    print(f'Say: "{prompt}"')
    print("Recording now. Press Enter when you finish speaking.")
    cancellation = CancellationToken()
    recording_task = asyncio.create_task(_recorder(config).record_utterance(cancellation))
    await asyncio.to_thread(input)
    cancellation.request_stop()
    audio = await recording_task
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(audio)
    print(f"Saved private voice fixture: {output_path.resolve()}")


async def replay_fixture(config: AppConfig, input_path: Path, turns: int) -> None:
    audio = input_path.read_bytes()
    controller = VoiceReplayController(audio, summary_interval=turns)
    app = build_application(
        config,
        interaction_mode="voice",
        trigger_override=controller.trigger,
        recorder_override=controller.recorder,
        latency_observer=controller.observe,
    )
    await controller.run(app, turns=turns)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Record or replay a private DeskBob voice test")
    parser.add_argument("action", choices=("record", "replay"))
    parser.add_argument("--config", type=Path, default=Path("configs/windows.yaml"))
    parser.add_argument("--audio", type=Path, default=DEFAULT_FIXTURE)
    parser.add_argument("--prompt", default="Say hello in one sentence.")
    parser.add_argument("--turns", type=int, default=1)
    return parser.parse_args(argv)


async def async_main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    load_dotenv()
    config = load_config(args.config)
    if args.action == "record":
        await record_fixture(config, args.audio, args.prompt)
    else:
        if not args.audio.is_file():
            raise RuntimeError(
                f"Voice fixture does not exist: {args.audio}. Record it once before replaying."
            )
        await replay_fixture(config, args.audio, args.turns)
    return 0


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    raise SystemExit(asyncio.run(async_main()))


if __name__ == "__main__":
    main()
