from __future__ import annotations

import logging
import math
from dataclasses import dataclass

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class VoiceLatencySample:
    """Completed timing information for one push-to-talk voice turn."""

    recording_seconds: float
    transcription_seconds: float
    model_seconds: float
    synthesis_seconds: float
    playback_seconds: float
    release_to_transcript_seconds: float
    release_to_response_seconds: float
    release_to_audio_seconds: float
    total_turn_seconds: float
    release_to_commit_seconds: float = 0.0
    commit_to_server_audio_seconds: float = 0.0
    server_audio_to_speaker_seconds: float = 0.0
    tool_seconds: float = 0.0


def format_voice_latency(sample: VoiceLatencySample) -> str:
    """Return one compact, human-readable timing waterfall."""
    transport = ""
    if (
        sample.release_to_commit_seconds
        or sample.commit_to_server_audio_seconds
        or sample.server_audio_to_speaker_seconds
        or sample.tool_seconds
    ):
        transport = (
            f"commit={_milliseconds(sample.release_to_commit_seconds)}ms + "
            f"server={_milliseconds(sample.commit_to_server_audio_seconds)}ms + "
            f"speaker={_milliseconds(sample.server_audio_to_speaker_seconds)}ms + "
            f"tools={_milliseconds(sample.tool_seconds)}ms | "
        )
    return (
        "Voice timeline: "
        f"record={_milliseconds(sample.recording_seconds)}ms | "
        f"release->transcript={_milliseconds(sample.release_to_transcript_seconds)}ms | "
        f"release->response={_milliseconds(sample.release_to_response_seconds)}ms | "
        f"release->audio={_milliseconds(sample.release_to_audio_seconds)}ms | "
        f"{transport}"
        "stages="
        f"{_milliseconds(sample.transcription_seconds)}ms STT + "
        f"{_milliseconds(sample.model_seconds)}ms model + "
        f"{_milliseconds(sample.synthesis_seconds)}ms TTS | "
        f"playback={_milliseconds(sample.playback_seconds)}ms | "
        f"total={_milliseconds(sample.total_turn_seconds)}ms"
    )


class VoiceLatencyTracker:
    """Accumulate voice timings and periodically log p50/p95 latency."""

    def __init__(self, *, summary_interval: int = 5) -> None:
        if summary_interval < 1:
            raise ValueError("summary_interval must be at least one")
        self._summary_interval = summary_interval
        self._samples: list[VoiceLatencySample] = []

    @property
    def samples(self) -> tuple[VoiceLatencySample, ...]:
        return tuple(self._samples)

    def observe(self, sample: VoiceLatencySample) -> None:
        self._samples.append(sample)
        if len(self._samples) % self._summary_interval != 0:
            return

        release_to_audio = [item.release_to_audio_seconds for item in self._samples]
        LOGGER.info(
            "Voice latency summary (%d turns): release-to-audio p50=%dms p95=%dms best=%dms",
            len(self._samples),
            _milliseconds(_percentile(release_to_audio, 0.50)),
            _milliseconds(_percentile(release_to_audio, 0.95)),
            _milliseconds(min(release_to_audio)),
        )


def _milliseconds(seconds: float) -> int:
    return round(max(0.0, seconds) * 1000)


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        raise ValueError("values must not be empty")
    ordered = sorted(values)
    position = (len(ordered) - 1) * percentile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction
