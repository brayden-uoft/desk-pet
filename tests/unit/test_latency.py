import logging

import pytest

from desk_pet.latency import VoiceLatencySample, VoiceLatencyTracker, format_voice_latency


def _sample(release_to_audio_seconds: float) -> VoiceLatencySample:
    return VoiceLatencySample(
        recording_seconds=1.2,
        transcription_seconds=0.2,
        model_seconds=0.4,
        synthesis_seconds=0.3,
        playback_seconds=1.5,
        release_to_transcript_seconds=0.2,
        release_to_response_seconds=0.6,
        release_to_audio_seconds=release_to_audio_seconds,
        total_turn_seconds=3.6,
    )


def test_formats_voice_timing_waterfall_in_milliseconds() -> None:
    assert format_voice_latency(_sample(0.9)) == (
        "Voice timeline: record=1200ms | release->transcript=200ms | "
        "release->response=600ms | release->audio=900ms | "
        "stages=200ms STT + 400ms model + 300ms TTS | playback=1500ms | total=3600ms"
    )


def test_tracker_logs_rolling_p50_and_p95(caplog: pytest.LogCaptureFixture) -> None:
    tracker = VoiceLatencyTracker(summary_interval=5)

    with caplog.at_level(logging.INFO):
        for seconds in (0.5, 0.7, 0.9, 1.1, 1.3):
            tracker.observe(_sample(seconds))

    assert len(tracker.samples) == 5
    assert (
        "Voice latency summary (5 turns): release-to-audio p50=900ms p95=1260ms best=500ms"
        in caplog.messages
    )


def test_tracker_rejects_invalid_summary_interval() -> None:
    with pytest.raises(ValueError, match="at least one"):
        VoiceLatencyTracker(summary_interval=0)
