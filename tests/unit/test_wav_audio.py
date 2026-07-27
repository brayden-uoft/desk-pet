import struct
import wave
from io import BytesIO

import pytest

from desk_pet.audio.errors import AudioCancelled, AudioError
from desk_pet.audio.wav import capture_wav, decode_wav, pcm_rms, playback_blocks
from desk_pet.hardware.interfaces import CancellationToken


def _pcm(value: int, frames: int = 4) -> bytes:
    return struct.pack(f"<{frames}h", *([value] * frames))


def test_pcm_rms_distinguishes_speech_from_silence() -> None:
    assert pcm_rms(_pcm(0)) == 0
    assert pcm_rms(_pcm(900)) == 900


def test_capture_stops_after_configured_post_speech_silence() -> None:
    blocks = iter([_pcm(1000), _pcm(0), _pcm(0), _pcm(0)])
    reads = 0

    def read_block(frames: int) -> bytes:
        nonlocal reads
        reads += 1
        return next(blocks)

    audio = capture_wav(
        read_block,
        cancellation=CancellationToken(),
        sample_rate_hz=40,
        block_duration_ms=100,
        silence_timeout_ms=200,
        maximum_recording_seconds=1,
        silence_threshold=500,
    )

    assert reads == 3
    with wave.open(BytesIO(audio), "rb") as wav_file:
        assert wav_file.getframerate() == 40
        assert wav_file.getnchannels() == 1
        assert wav_file.getnframes() == 12


def test_capture_always_stops_at_hard_timeout_without_speech() -> None:
    reads = 0

    def read_block(frames: int) -> bytes:
        nonlocal reads
        reads += 1
        return _pcm(0, frames)

    capture_wav(
        read_block,
        cancellation=CancellationToken(),
        sample_rate_hz=100,
        block_duration_ms=100,
        silence_timeout_ms=200,
        maximum_recording_seconds=0.3,
        silence_threshold=500,
    )

    assert reads == 3


def test_capture_rejects_cancelled_recording() -> None:
    cancellation = CancellationToken()
    cancellation.cancel()

    with pytest.raises(AudioCancelled):
        capture_wav(
            lambda frames: _pcm(0, frames),
            cancellation=cancellation,
            sample_rate_hz=100,
            block_duration_ms=100,
            silence_timeout_ms=200,
            maximum_recording_seconds=1,
            silence_threshold=500,
        )


def test_decode_rejects_invalid_wav() -> None:
    with pytest.raises(AudioError, match="not valid WAV"):
        decode_wav(b"not-a-wav")


def test_playback_stops_when_cancelled() -> None:
    cancellation = CancellationToken()
    written: list[bytes] = []

    def write(block: bytes) -> None:
        written.append(block)
        cancellation.cancel()

    with pytest.raises(AudioCancelled):
        playback_blocks([b"one", b"two"], write, cancellation=cancellation)

    assert written == [b"one"]
