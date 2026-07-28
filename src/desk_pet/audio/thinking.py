from __future__ import annotations

import asyncio
import io
import logging
import math
import random
import struct
import wave
from contextlib import suppress
from typing import Protocol

from desk_pet.audio.errors import AudioCancelled, AudioError
from desk_pet.hardware.interfaces import AudioPlayer, CancellationToken

LOGGER = logging.getLogger(__name__)
SAMPLE_RATE_HZ = 16_000


class ThinkingAudio(Protocol):
    async def prepare(self) -> None:
        """Prepare reusable interaction audio before the first interaction."""

    async def listen_started(self) -> None:
        """Play a non-blocking acknowledgement when push-to-talk begins."""

    async def start(self) -> None:
        """Acknowledge push-to-talk release and begin thinking audio."""

    async def stop(self) -> None:
        """Stop thinking audio before the final answer starts."""


def generate_button_cue_wav(*, pressed: bool, volume: float = 0.18) -> bytes:
    """Create a short synthetic push-to-talk engage/release cue."""
    duration = 0.13
    sample_count = round(SAMPLE_RATE_HZ * duration)
    samples: list[float] = []
    start_hz, end_hz = (620.0, 1080.0) if pressed else (980.0, 430.0)
    phase = 0.0
    for index in range(sample_count):
        progress = index / max(1, sample_count - 1)
        frequency = start_hz + (end_hz - start_hz) * progress
        phase += math.tau * frequency / SAMPLE_RATE_HZ
        envelope = math.sin(math.pi * progress) ** 1.5
        metallic = math.sin(phase) + 0.34 * math.sin(phase * 2.01)
        samples.append(volume * envelope * metallic / 1.34)
    return _encode_wav(samples)


def generate_mechanical_thinking_wav(
    *,
    duration_seconds: float = 4.2,
    volume: float = 0.16,
    seed: int | None = None,
    release_cue: bool = False,
) -> bytes:
    """Create a tiny robot-brain soundscape from gears, relays, and chirps."""
    rng = random.Random(seed)
    sample_count = round(SAMPLE_RATE_HZ * duration_seconds)
    samples = [0.0] * sample_count
    motor_hz = rng.uniform(82.0, 98.0)
    drift_segment_samples = round(SAMPLE_RATE_HZ * rng.uniform(0.42, 0.78))
    drift_point_count = sample_count // drift_segment_samples + 2
    pitch_drift = [rng.uniform(-4.0, 4.0) for _ in range(drift_point_count)]
    drive_levels = [rng.uniform(0.65, 0.90) for _ in range(drift_point_count)]
    motor_phase = 0.0

    for index in range(sample_count):
        segment = index // drift_segment_samples
        segment_progress = (index % drift_segment_samples) / drift_segment_samples
        smooth_progress = segment_progress**2 * (3.0 - 2.0 * segment_progress)
        drift_hz = _interpolate(pitch_drift, segment, smooth_progress)
        drive = _interpolate(drive_levels, segment, smooth_progress)
        motor_phase += math.tau * (motor_hz + drift_hz) / SAMPLE_RATE_HZ
        gear = (
            0.42 * math.sin(motor_phase)
            + 0.18 * math.sin(2.03 * motor_phase)
            + 0.08 * math.sin(5.07 * motor_phase)
        )
        samples[index] += gear * drive

    click_count = max(4, round(duration_seconds * rng.uniform(2.0, 3.5)))
    for _ in range(click_count):
        click_start = rng.randrange(0, max(1, sample_count - 240))
        click_length = rng.randrange(45, 150)
        click_pitch = rng.uniform(1300.0, 3100.0)
        click_strength = rng.uniform(0.35, 0.75)
        for offset in range(click_length):
            envelope = math.exp(-offset / max(7.0, click_length / 5.0))
            noise = rng.uniform(-1.0, 1.0)
            ring = math.sin(math.tau * click_pitch * offset / SAMPLE_RATE_HZ)
            samples[click_start + offset] += click_strength * envelope * (noise + ring)

    chirp_count = max(2, round(duration_seconds * rng.uniform(0.7, 1.3)))
    for _ in range(chirp_count):
        chirp_length = rng.randrange(700, 1800)
        chirp_start = rng.randrange(0, max(1, sample_count - chirp_length))
        start_hz = rng.uniform(420.0, 1050.0)
        sweep_hz = rng.uniform(-180.0, 420.0)
        chirp_phase = 0.0
        for offset in range(chirp_length):
            progress = offset / chirp_length
            chirp_phase += math.tau * (start_hz + sweep_hz * progress) / SAMPLE_RATE_HZ
            envelope = math.sin(math.pi * progress) ** 2
            samples[chirp_start + offset] += 0.24 * envelope * math.sin(chirp_phase)

    if release_cue:
        cue = _decode_pcm(generate_button_cue_wav(pressed=False, volume=0.22))
        for index, value in enumerate(cue):
            if index < sample_count:
                samples[index] += value

    fade_samples = min(round(0.025 * SAMPLE_RATE_HZ), sample_count // 2)
    for index in range(fade_samples):
        fade = index / max(1, fade_samples)
        samples[index] *= fade
        samples[-index - 1] *= fade
    peak = max(1.0, max(abs(sample) for sample in samples))
    return _encode_wav([volume * sample / peak for sample in samples])


class ThinkingAudioController:
    """Play immediate local interaction cues and varied mechanical thinking loops."""

    def __init__(
        self,
        *,
        player: AudioPlayer,
        volume: float = 0.16,
        clip_seconds: float = 4.2,
        clip_count: int = 4,
        seed: int | None = None,
    ) -> None:
        self._player = player
        self._volume = volume
        self._clip_seconds = clip_seconds
        self._clip_count = clip_count
        self._seed = seed
        self._press_cue: bytes | None = None
        self._clips: tuple[bytes, ...] = ()
        self._cue_cancellation: CancellationToken | None = None
        self._cue_task: asyncio.Task[None] | None = None
        self._cancellation: CancellationToken | None = None
        self._play_task: asyncio.Task[None] | None = None
        self._next_clip_index = 0

    async def prepare(self) -> None:
        seed_source = random.Random(self._seed)
        self._press_cue = generate_button_cue_wav(pressed=True)
        self._clips = tuple(
            generate_mechanical_thinking_wav(
                duration_seconds=self._clip_seconds,
                volume=self._volume,
                seed=seed_source.randrange(0, 2**31),
                release_cue=index == 0,
            )
            for index in range(self._clip_count)
        )

    async def listen_started(self) -> None:
        if self._press_cue is None:
            return
        await self._stop_cue()
        cancellation = CancellationToken()
        self._cue_cancellation = cancellation
        self._cue_task = asyncio.create_task(self._play_cue(self._press_cue, cancellation))
        await asyncio.sleep(0)

    async def start(self) -> None:
        if not self._clips or self._play_task is not None:
            return
        await self._stop_cue()
        self._cancellation = CancellationToken()
        starting_index = self._next_clip_index
        self._next_clip_index = (self._next_clip_index + 1) % len(self._clips)
        self._play_task = asyncio.create_task(self._play_loop(self._cancellation, starting_index))
        await asyncio.sleep(0)

    async def stop(self) -> None:
        await self._stop_cue()
        if self._play_task is None or self._cancellation is None:
            return
        self._cancellation.cancel()
        with suppress(AudioCancelled):
            await self._play_task
        self._play_task = None
        self._cancellation = None

    async def _stop_cue(self) -> None:
        if self._cue_task is None or self._cue_cancellation is None:
            return
        self._cue_cancellation.cancel()
        with suppress(AudioCancelled):
            await self._cue_task
        self._cue_task = None
        self._cue_cancellation = None

    async def _play_cue(self, audio: bytes, cancellation: CancellationToken) -> None:
        try:
            await self._player.play(audio, cancellation)
        except AudioCancelled:
            raise
        except AudioError:
            LOGGER.warning("Push-to-talk audio cue could not be played")

    async def _play_loop(
        self,
        cancellation: CancellationToken,
        clip_index: int,
    ) -> None:
        while not cancellation.cancelled:
            clip = self._clips[clip_index % len(self._clips)]
            clip_index += 1
            await self._player.play(clip, cancellation)


def _encode_wav(samples: list[float]) -> bytes:
    pcm = b"".join(
        struct.pack("<h", round(max(-1.0, min(1.0, sample)) * 32767)) for sample in samples
    )
    output = io.BytesIO()
    with wave.open(output, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(SAMPLE_RATE_HZ)
        wav_file.writeframes(pcm)
    return output.getvalue()


def _decode_pcm(audio: bytes) -> list[float]:
    with wave.open(io.BytesIO(audio), "rb") as wav_file:
        frames = wav_file.readframes(wav_file.getnframes())
    return [sample[0] / 32767.0 for sample in struct.iter_unpack("<h", frames)]


def _interpolate(values: list[float], index: int, progress: float) -> float:
    return values[index] + (values[index + 1] - values[index]) * progress
