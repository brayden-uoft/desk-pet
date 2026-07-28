from __future__ import annotations

import asyncio
from types import TracebackType

import pytest

from desk_pet.audio.errors import AudioCancelled
from desk_pet.audio.thinking import generate_mechanical_thinking_wav
from desk_pet.hardware.desktop import sounddevice_audio
from desk_pet.hardware.desktop.sounddevice_audio import SoundDevicePlayer
from desk_pet.hardware.interfaces import CancellationToken


class FakeOutputStream:
    def __init__(self, cancellation: CancellationToken) -> None:
        self._cancellation = cancellation
        self.aborted = False
        self.write_count = 0

    def __enter__(self) -> FakeOutputStream:
        return self

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        return None

    def write(self, _block: bytes) -> None:
        self.write_count += 1
        self._cancellation.cancel()

    def abort(self, ignore_errors: bool = True) -> None:
        del ignore_errors
        self.aborted = True


class FakeSoundDevice:
    def __init__(self, stream: FakeOutputStream) -> None:
        self._stream = stream

    def RawOutputStream(self, **_arguments: object) -> FakeOutputStream:
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
