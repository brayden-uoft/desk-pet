from __future__ import annotations

import asyncio
import importlib
import queue
import sys
import threading
from array import array
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator
from functools import lru_cache
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
        channels: int = 1,
    ) -> None:
        self._sample_rate_hz = sample_rate_hz
        self._block_duration_ms = block_duration_ms
        self._silence_timeout_ms = silence_timeout_ms
        self._maximum_recording_seconds = maximum_recording_seconds
        self._silence_threshold = silence_threshold
        self._device = device
        self._channels = channels

    async def record_utterance(self, cancellation: CancellationToken) -> bytes:
        return await asyncio.to_thread(self._record, cancellation)

    async def record_utterance_stream(
        self,
        cancellation: CancellationToken,
        on_pcm_chunk: Callable[[bytes], Awaitable[None]],
    ) -> bytes:
        loop = asyncio.get_running_loop()
        chunks: asyncio.Queue[bytes | None] = asyncio.Queue()

        def emit(block: bytes) -> None:
            pcm_24khz = _resample_pcm16(block, 1, self._sample_rate_hz, 24_000)
            loop.call_soon_threadsafe(chunks.put_nowait, pcm_24khz)

        def record() -> bytes:
            try:
                return self._record(cancellation, emit)
            finally:
                loop.call_soon_threadsafe(chunks.put_nowait, None)

        recording_task = asyncio.create_task(asyncio.to_thread(record))
        while True:
            chunk = await chunks.get()
            if chunk is None:
                break
            await on_pcm_chunk(chunk)
        return await recording_task

    def _record(
        self,
        cancellation: CancellationToken,
        on_block: Callable[[bytes], None] | None = None,
    ) -> bytes:
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
                channels=self._channels,
                dtype="int16",
            ) as stream:

                def read_block(frames: int) -> bytes:
                    data, _overflowed = stream.read(frames)
                    return _downmix_pcm16(bytes(data), self._channels)

                return capture_wav(
                    read_block,
                    cancellation=cancellation,
                    sample_rate_hz=self._sample_rate_hz,
                    block_duration_ms=self._block_duration_ms,
                    silence_timeout_ms=self._silence_timeout_ms,
                    maximum_recording_seconds=self._maximum_recording_seconds,
                    silence_threshold=self._silence_threshold,
                    stop_on_silence=False,
                    on_block=on_block,
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
        volume: float = 0.7,
        output_sample_rate_hz: int | None = None,
        output_channels: int | None = None,
    ) -> None:
        self._device = device
        self._block_duration_ms = block_duration_ms
        self._volume = min(1.0, max(0.0, volume))
        self._output_sample_rate_hz = output_sample_rate_hz
        self._output_channels = output_channels
        self._muted = False
        self._control_lock = threading.Lock()
        self._playback_lock = threading.Lock()
        self._stream: Any | None = None
        self._stream_context: Any | None = None

    @property
    def volume(self) -> float:
        with self._control_lock:
            return self._volume

    @property
    def muted(self) -> bool:
        with self._control_lock:
            return self._muted

    def set_volume(self, volume: float) -> None:
        with self._control_lock:
            self._volume = min(1.0, max(0.0, volume))

    def set_muted(self, muted: bool) -> None:
        with self._control_lock:
            self._muted = muted

    async def play(self, audio: bytes, cancellation: CancellationToken) -> None:
        await asyncio.to_thread(self._play, audio, cancellation)

    async def prepare(self) -> None:
        await asyncio.to_thread(self._prepare)

    async def close(self) -> None:
        await asyncio.to_thread(self._close_stream)

    def _prepare(self) -> None:
        with self._playback_lock:
            self._ensure_stream()

    async def play_pcm_stream(
        self,
        chunks: AsyncIterator[bytes],
        cancellation: CancellationToken,
        on_audio_started: Callable[[], None],
    ) -> None:
        audio_queue: queue.Queue[bytes | None] = queue.Queue()
        loop = asyncio.get_running_loop()

        def report_audio_started() -> None:
            loop.call_soon_threadsafe(on_audio_started)

        playback = asyncio.create_task(
            asyncio.to_thread(
                self._play_pcm_queue,
                audio_queue,
                cancellation,
                report_audio_started,
            )
        )
        try:
            async for chunk in chunks:
                if cancellation.cancelled:
                    raise AudioCancelled("Speech playback cancelled.")
                audio_queue.put_nowait(chunk)
        finally:
            audio_queue.put_nowait(None)
        await playback

    def _play(self, audio: bytes, cancellation: CancellationToken) -> None:
        sample_rate, channels, sample_width, frames = decode_wav(audio)
        if sample_width != 2:
            raise AudioError("Only 16-bit WAV speech playback is supported.")
        output_sample_rate = self._output_sample_rate_hz or 24_000
        frames = _resample_pcm16(frames, channels, sample_rate, output_sample_rate)
        output_channels = self._output_channels or channels
        frames = _convert_pcm16_channels(frames, channels, output_channels)
        bytes_per_frame = sample_width * output_channels
        frames_per_block = max(1, output_sample_rate * self._block_duration_ms // 1000)
        block_size = frames_per_block * bytes_per_frame
        try:
            with self._playback_lock:
                stream = self._ensure_stream()
                try:
                    playback_blocks(
                        self._controlled_chunks(frames, block_size),
                        stream.write,
                        cancellation=cancellation,
                    )
                except AudioCancelled:
                    # Closing an active PortAudio stream normally drains queued
                    # samples. Abort first so Escape discards buffered speech
                    # instead of audibly continuing during context-manager exit.
                    stream.abort()
                    self._close_stream()
                    raise
        except AudioError:
            raise
        except Exception as exc:
            raise AudioError(f"Audio playback failed: {exc}") from exc

    def _play_pcm_queue(
        self,
        audio_queue: queue.Queue[bytes | None],
        cancellation: CancellationToken,
        on_audio_started: Callable[[], None],
    ) -> None:
        source_rate = 24_000
        source_channels = 1
        output_sample_rate = self._output_sample_rate_hz or source_rate
        output_channels = self._output_channels or source_channels
        started = False
        try:
            with self._playback_lock:
                stream = self._ensure_stream()
                try:
                    while True:
                        block = audio_queue.get()
                        if block is None:
                            break
                        if cancellation.cancelled:
                            raise AudioCancelled("Speech playback cancelled.")
                        block = _resample_pcm16(
                            block,
                            source_channels,
                            source_rate,
                            output_sample_rate,
                        )
                        block = _convert_pcm16_channels(
                            block,
                            source_channels,
                            output_channels,
                        )
                        with self._control_lock:
                            gain = 0.0 if self._muted else self._volume
                        if not started:
                            started = True
                            on_audio_started()
                        stream.write(_scale_pcm16(block, gain))
                except AudioCancelled:
                    stream.abort()
                    self._close_stream()
                    raise
        except AudioError:
            raise
        except Exception as exc:
            raise AudioError(f"Streaming audio playback failed: {exc}") from exc

    def _ensure_stream(self) -> Any:
        if self._stream is not None:
            return self._stream
        sounddevice = _sounddevice()
        output_sample_rate = self._output_sample_rate_hz or 24_000
        output_channels = self._output_channels or 1
        frames_per_block = max(
            1,
            output_sample_rate * self._block_duration_ms // 1000,
        )
        context = sounddevice.RawOutputStream(
            samplerate=output_sample_rate,
            blocksize=frames_per_block,
            device=self._device,
            channels=output_channels,
            dtype="int16",
        )
        self._stream_context = context
        self._stream = context.__enter__()
        return self._stream

    def _close_stream(self) -> None:
        context, self._stream_context = self._stream_context, None
        self._stream = None
        if context is not None:
            context.__exit__(None, None, None)

    def _controlled_chunks(self, data: bytes, size: int) -> Iterator[bytes]:
        for block in _chunks(data, size):
            with self._control_lock:
                gain = 0.0 if self._muted else self._volume
            yield _scale_pcm16(block, gain)


def _chunks(data: bytes, size: int) -> Iterator[bytes]:
    for start in range(0, len(data), size):
        yield data[start : start + size]


def _scale_pcm16(data: bytes, gain: float) -> bytes:
    if gain == 1.0:
        return data
    samples = array("h")
    samples.frombytes(data)
    if sys.byteorder != "little":
        samples.byteswap()
    for index, sample in enumerate(samples):
        samples[index] = max(-32768, min(32767, round(sample * gain)))
    if sys.byteorder != "little":
        samples.byteswap()
    return samples.tobytes()


def _downmix_pcm16(data: bytes, channels: int) -> bytes:
    if channels == 1:
        return data
    samples = array("h")
    samples.frombytes(data)
    if sys.byteorder != "little":
        samples.byteswap()
    mixed = array(
        "h",
        (
            round(sum(samples[start : start + channels]) / channels)
            for start in range(0, len(samples) - channels + 1, channels)
        ),
    )
    if sys.byteorder != "little":
        mixed.byteswap()
    return mixed.tobytes()


@lru_cache(maxsize=16)
def _resample_pcm16(data: bytes, channels: int, source_rate: int, target_rate: int) -> bytes:
    """Linearly resample interleaved signed 16-bit PCM without platform codecs."""
    if source_rate == target_rate or not data:
        return data
    samples = array("h")
    samples.frombytes(data)
    if sys.byteorder != "little":
        samples.byteswap()
    frame_count = len(samples) // channels
    if frame_count < 2:
        return data
    target_frame_count = max(1, round(frame_count * target_rate / source_rate))
    output = array("h")
    for target_index in range(target_frame_count):
        source_position = target_index * source_rate / target_rate
        left_frame = min(int(source_position), frame_count - 1)
        right_frame = min(left_frame + 1, frame_count - 1)
        fraction = source_position - left_frame
        for channel in range(channels):
            left = samples[left_frame * channels + channel]
            right = samples[right_frame * channels + channel]
            output.append(round(left + (right - left) * fraction))
    if sys.byteorder != "little":
        output.byteswap()
    return output.tobytes()


def _convert_pcm16_channels(data: bytes, source_channels: int, target_channels: int) -> bytes:
    if source_channels == target_channels:
        return data
    if source_channels != 1:
        raise AudioError(
            f"Cannot convert {source_channels}-channel audio to {target_channels} channels."
        )
    samples = array("h")
    samples.frombytes(data)
    if sys.byteorder != "little":
        samples.byteswap()
    converted = array("h", (sample for sample in samples for _ in range(target_channels)))
    if sys.byteorder != "little":
        converted.byteswap()
    return converted.tobytes()
