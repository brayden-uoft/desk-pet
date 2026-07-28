from __future__ import annotations

import asyncio
import importlib
from collections.abc import Iterator
from typing import Any

from desk_pet.audio.errors import AudioCancelled, AudioError
from desk_pet.audio.wav import capture_wav, decode_wav, playback_blocks
from desk_pet.hardware.interfaces import CancellationToken


def _sounddevice() -> Any:
    try:
        return importlib.import_module("sounddevice")
    except ImportError as exc:
        raise AudioError(
            "The sounddevice package is unavailable. Run the Windows launcher again."
        ) from exc


class SoundDeviceRecorder:
    def __init__(
        self,
        *,
        sample_rate_hz: int,
        block_duration_ms: int,
        silence_timeout_ms: int,
        maximum_recording_seconds: float,
        silence_threshold: float,
        device: str | int | None = None,
    ) -> None:
        self._sample_rate_hz = sample_rate_hz
        self._block_duration_ms = block_duration_ms
        self._silence_timeout_ms = silence_timeout_ms
        self._maximum_recording_seconds = maximum_recording_seconds
        self._silence_threshold = silence_threshold
        self._device = device

    async def record_utterance(self, cancellation: CancellationToken) -> bytes:
        return await asyncio.to_thread(self._record, cancellation)

    def _record(self, cancellation: CancellationToken) -> bytes:
        sounddevice = _sounddevice()
        frames_per_block = max(
            1,
            self._sample_rate_hz * self._block_duration_ms // 1000,
        )
        try:
            with sounddevice.RawInputStream(
                samplerate=self._sample_rate_hz,
                blocksize=frames_per_block,
                device=self._device,
                channels=1,
                dtype="int16",
            ) as stream:

                def read_block(frames: int) -> bytes:
                    data, _overflowed = stream.read(frames)
                    return bytes(data)

                return capture_wav(
                    read_block,
                    cancellation=cancellation,
                    sample_rate_hz=self._sample_rate_hz,
                    block_duration_ms=self._block_duration_ms,
                    silence_timeout_ms=self._silence_timeout_ms,
                    maximum_recording_seconds=self._maximum_recording_seconds,
                    silence_threshold=self._silence_threshold,
                    stop_on_silence=False,
                )
        except AudioError:
            raise
        except Exception as exc:
            raise AudioError(f"Microphone recording failed: {exc}") from exc


class SoundDevicePlayer:
    def __init__(
        self,
        *,
        device: str | int | None = None,
        block_duration_ms: int = 50,
    ) -> None:
        self._device = device
        self._block_duration_ms = block_duration_ms

    async def play(self, audio: bytes, cancellation: CancellationToken) -> None:
        await asyncio.to_thread(self._play, audio, cancellation)

    def _play(self, audio: bytes, cancellation: CancellationToken) -> None:
        sample_rate, channels, sample_width, frames = decode_wav(audio)
        if sample_width != 2:
            raise AudioError("Only 16-bit WAV speech playback is supported.")
        bytes_per_frame = sample_width * channels
        frames_per_block = max(1, sample_rate * self._block_duration_ms // 1000)
        block_size = frames_per_block * bytes_per_frame
        sounddevice = _sounddevice()
        try:
            with sounddevice.RawOutputStream(
                samplerate=sample_rate,
                blocksize=frames_per_block,
                device=self._device,
                channels=channels,
                dtype="int16",
            ) as stream:
                try:
                    playback_blocks(
                        _chunks(frames, block_size),
                        stream.write,
                        cancellation=cancellation,
                    )
                except AudioCancelled:
                    # Closing an active PortAudio stream normally drains queued
                    # samples. Abort first so Escape discards buffered speech
                    # instead of audibly continuing during context-manager exit.
                    stream.abort()
                    raise
        except AudioError:
            raise
        except Exception as exc:
            raise AudioError(f"Audio playback failed: {exc}") from exc


def _chunks(data: bytes, size: int) -> Iterator[bytes]:
    for start in range(0, len(data), size):
        yield data[start : start + size]
