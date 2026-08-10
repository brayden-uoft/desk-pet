from __future__ import annotations

import io
import wave

import pytest

from desk_pet.audio.realtime import OpenAIRealtimeVoice, wav_to_realtime_pcm
from desk_pet.realtime_replay import _summary


def _wav(*, sample_rate: int = 12_000, channels: int = 1, width: int = 2) -> bytes:
    output = io.BytesIO()
    with wave.open(output, "wb") as audio:
        audio.setframerate(sample_rate)
        audio.setnchannels(channels)
        audio.setsampwidth(width)
        audio.writeframes(b"\x00" * (sample_rate * channels * width // 10))
    return output.getvalue()


def test_wav_is_converted_to_24khz_mono_pcm() -> None:
    pcm = wav_to_realtime_pcm(_wav())
    assert len(pcm) == 4_800


def test_realtime_replay_rejects_multichannel_fixture() -> None:
    with pytest.raises(ValueError, match="mono"):
        wav_to_realtime_pcm(_wav(channels=2))


def test_summary_reports_measured_distribution() -> None:
    assert _summary([900.0, 1_100.0, 1_000.0]) == (
        "Realtime latency summary (3 turns): "
        "release-to-first-audio p50=1000ms p95=1100ms best=900ms"
    )


def test_realtime_session_has_full_spoken_response_headroom() -> None:
    voice = OpenAIRealtimeVoice(
        client=None,  # type: ignore[arg-type]
        player=None,  # type: ignore[arg-type]
        model="realtime-test",
        voice="echo",
        speed=1.5,
        instructions="Test instructions",
    )
    assert voice._session_config()["max_output_tokens"] == 4_096
