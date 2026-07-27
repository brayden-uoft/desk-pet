from __future__ import annotations

import io
import math
import sys
import wave
from array import array
from collections.abc import Callable, Iterable

from desk_pet.audio.errors import AudioCancelled, AudioError
from desk_pet.hardware.interfaces import CancellationToken

BlockReader = Callable[[int], bytes]
BlockWriter = Callable[[bytes], None]


def pcm_rms(block: bytes) -> float:
    """Return the RMS amplitude for little-endian signed 16-bit PCM."""
    if not block:
        return 0.0
    samples = array("h")
    samples.frombytes(block)
    if sys.byteorder == "big":
        samples.byteswap()
    if not samples:
        return 0.0
    return math.sqrt(sum(sample * sample for sample in samples) / len(samples))


def capture_wav(
    read_block: BlockReader,
    *,
    cancellation: CancellationToken,
    sample_rate_hz: int,
    block_duration_ms: int,
    silence_timeout_ms: int,
    maximum_recording_seconds: float,
    silence_threshold: float,
) -> bytes:
    """Capture blocks until post-speech silence or the hard recording limit."""
    frames_per_block = max(1, sample_rate_hz * block_duration_ms // 1000)
    maximum_blocks = max(
        1,
        math.ceil(maximum_recording_seconds * 1000 / block_duration_ms),
    )
    silence_blocks_required = max(1, math.ceil(silence_timeout_ms / block_duration_ms))
    silent_blocks = 0
    heard_speech = False
    blocks: list[bytes] = []

    for _ in range(maximum_blocks):
        if cancellation.cancelled:
            raise AudioCancelled("Recording cancelled.")
        block = read_block(frames_per_block)
        blocks.append(block)
        if pcm_rms(block) >= silence_threshold:
            heard_speech = True
            silent_blocks = 0
        elif heard_speech:
            silent_blocks += 1
            if silent_blocks >= silence_blocks_required:
                break

    if cancellation.cancelled:
        raise AudioCancelled("Recording cancelled.")

    output = io.BytesIO()
    with wave.open(output, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate_hz)
        wav_file.writeframes(b"".join(blocks))
    return output.getvalue()


def decode_wav(audio: bytes) -> tuple[int, int, int, bytes]:
    """Decode WAV bytes into sample rate, channels, width, and PCM frames."""
    try:
        with wave.open(io.BytesIO(audio), "rb") as wav_file:
            return (
                wav_file.getframerate(),
                wav_file.getnchannels(),
                wav_file.getsampwidth(),
                wav_file.readframes(wav_file.getnframes()),
            )
    except (EOFError, wave.Error) as exc:
        raise AudioError("The generated speech was not valid WAV audio.") from exc


def playback_blocks(
    blocks: Iterable[bytes],
    write_block: BlockWriter,
    *,
    cancellation: CancellationToken,
) -> None:
    for block in blocks:
        if cancellation.cancelled:
            raise AudioCancelled("Playback cancelled.")
        write_block(block)
    if cancellation.cancelled:
        raise AudioCancelled("Playback cancelled.")
