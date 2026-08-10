from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from types import TracebackType

import pytest

from desk_pet.audio.errors import AudioCancelled
from desk_pet.audio.thinking import generate_mechanical_thinking_wav
from desk_pet.hardware.desktop import sounddevice_audio
from desk_pet.hardware.desktop.sounddevice_audio import (
    SoundDevicePlayer,
    _convert_pcm16_channels,
    _downmix_pcm16,
    _resample_pcm16,
    _scale_pcm16,
)
from desk_pet.hardware.interfaces import CancellationToken


class FakeOutputStream:
    def __init__(self, cancellation: CancellationToken, *, cancel_on_write: bool = True) -> None:
        self._cancellation = cancellation
        self._cancel_on_write = cancel_on_write
        self.aborted = False
        self.write_count = 0
        self.enter_count = 0
        self.exit_count = 0

    def __enter__(self) -> FakeOutputStream:
        self.enter_count += 1
        return self

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.exit_count += 1
        return None

    def write(self, _block: bytes) -> None:
        self.write_count += 1
        if self._cancel_on_write:
            self._cancellation.cancel()

    def abort(self, ignore_errors: bool = True) -> None:
        del ignore_errors
        self.aborted = True


class FakeSoundDevice:
    def __init__(self, stream: FakeOutputStream) -> None:
        self._stream = stream
        self.output_arguments: dict[str, object] = {}

    def RawOutputStream(self, **arguments: object) -> FakeOutputStream:
        self.output_arguments = arguments
        return self._stream


def test_player_aborts_stream_when_playback_is_cancelled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cancellation = CancellationToken()
    stream = FakeOutputStream(cancellation)
    sounddevice = FakeSoundDevice(stream)
    monkeypatch.setattr(sounddevice_audio, "_sounddevice", lambda: sounddevice)
    player = SoundDevicePlayer(block_duration_ms=10)
    audio = generate_mechanical_thinking_wav(duration_seconds=0.2, seed=4)

    with pytest.raises(AudioCancelled):
        asyncio.run(player.play(audio, cancellation))

    assert stream.write_count == 1
    assert stream.aborted


def test_player_uses_configured_hardware_sample_rate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cancellation = CancellationToken()
    stream = FakeOutputStream(cancellation)
    sounddevice = FakeSoundDevice(stream)
    monkeypatch.setattr(sounddevice_audio, "_sounddevice", lambda: sounddevice)
    player = SoundDevicePlayer(output_sample_rate_hz=48_000, output_channels=2)

    with pytest.raises(AudioCancelled):
        asyncio.run(
            player.play(generate_mechanical_thinking_wav(duration_seconds=0.2), cancellation)
        )

    assert sounddevice.output_arguments["samplerate"] == 48_000
    assert sounddevice.output_arguments["channels"] == 2


def test_player_streams_pcm_and_reports_first_audio(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def scenario() -> None:
        cancellation = CancellationToken()
        stream = FakeOutputStream(cancellation, cancel_on_write=False)
        sounddevice = FakeSoundDevice(stream)
        monkeypatch.setattr(sounddevice_audio, "_sounddevice", lambda: sounddevice)
        player = SoundDevicePlayer(volume=1.0)
        starts = 0

        def started() -> None:
            nonlocal starts
            starts += 1

        async def chunks() -> AsyncIterator[bytes]:
            for chunk in (b"\x01\x00" * 100, b"\x02\x00" * 100):
                yield chunk

        await player.play_pcm_stream(chunks(), cancellation, started)

        assert starts == 1
        assert stream.write_count == 2
        assert sounddevice.output_arguments["samplerate"] == 24_000
        assert sounddevice.output_arguments["channels"] == 1

    asyncio.run(scenario())


def test_player_prewarms_and_reuses_one_output_stream(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def scenario() -> None:
        cancellation = CancellationToken()
        stream = FakeOutputStream(cancellation, cancel_on_write=False)
        sounddevice = FakeSoundDevice(stream)
        monkeypatch.setattr(sounddevice_audio, "_sounddevice", lambda: sounddevice)
        player = SoundDevicePlayer(volume=1.0)

        await player.prepare()
        await player.play(generate_mechanical_thinking_wav(duration_seconds=0.2), cancellation)
        await player.play(generate_mechanical_thinking_wav(duration_seconds=0.2), cancellation)
        await player.close()

        assert stream.enter_count == 1
        assert stream.exit_count == 1
        assert stream.write_count > 2

    asyncio.run(scenario())


def test_player_volume_and_mute_controls_are_bounded() -> None:
    player = SoundDevicePlayer(volume=0.7)

    player.set_volume(1.5)
    player.set_muted(True)
    assert player.volume == 1.0
    assert player.muted

    player.set_volume(-1)
    player.set_muted(False)
    assert player.volume == 0.0
    assert not player.muted


def test_pcm_scaling_changes_16_bit_samples() -> None:
    assert _scale_pcm16(b"\xe8\x03\x18\xfc", 0.5) == b"\xf4\x01\x0c\xfe"


def test_stereo_pcm_is_downmixed_to_mono() -> None:
    assert _downmix_pcm16(b"\xe8\x03\xb8\x0b\x18\xfc\x48\xf4", 2) == (b"\xd0\x07\x30\xf8")


def test_pcm_is_resampled_to_configured_output_rate() -> None:
    source = b"\x00\x00\xe8\x03\xd0\x07"

    assert _resample_pcm16(source, 1, 3, 6) == (b"\x00\x00\xf4\x01\xe8\x03\xdc\x05\xd0\x07\xd0\x07")


def test_mono_pcm_is_duplicated_to_stereo() -> None:
    assert _convert_pcm16_channels(b"\xe8\x03\x18\xfc", 1, 2) == (
        b"\xe8\x03\xe8\x03\x18\xfc\x18\xfc"
    )
