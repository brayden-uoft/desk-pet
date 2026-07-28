import asyncio
import io
import wave

from desk_pet.audio.errors import AudioCancelled
from desk_pet.audio.thinking import (
    SAMPLE_RATE_HZ,
    ThinkingAudioController,
    generate_button_cue_wav,
    generate_mechanical_thinking_wav,
)
from desk_pet.hardware.interfaces import CancellationToken


class RecordingCancellablePlayer:
    def __init__(self) -> None:
        self.audio: list[bytes] = []
        self.started = asyncio.Event()
        self.cancel_count = 0

    async def play(self, audio: bytes, cancellation: CancellationToken) -> None:
        self.audio.append(audio)
        self.started.set()
        while not cancellation.cancelled:
            await asyncio.sleep(0)
        self.cancel_count += 1
        raise AudioCancelled("Playback cancelled.")


def test_generated_machine_audio_is_valid_varied_mono_wav() -> None:
    first = generate_mechanical_thinking_wav(seed=1, duration_seconds=1.0)
    same = generate_mechanical_thinking_wav(seed=1, duration_seconds=1.0)
    different = generate_mechanical_thinking_wav(seed=2, duration_seconds=1.0)

    assert first == same
    assert first != different
    with wave.open(io.BytesIO(first), "rb") as wav_file:
        assert wav_file.getnchannels() == 1
        assert wav_file.getsampwidth() == 2
        assert wav_file.getframerate() == SAMPLE_RATE_HZ
        assert wav_file.getnframes() == SAMPLE_RATE_HZ


def test_press_and_release_cues_are_distinct() -> None:
    assert generate_button_cue_wav(pressed=True) != generate_button_cue_wav(pressed=False)


def test_thinking_audio_cues_and_loop_stop_cleanly() -> None:
    async def scenario() -> None:
        player = RecordingCancellablePlayer()
        controller = ThinkingAudioController(
            player=player,
            clip_seconds=1.0,
            clip_count=2,
            seed=7,
        )

        await controller.prepare()
        await controller.listen_started()
        await player.started.wait()
        await controller.start()
        await asyncio.sleep(0)
        await controller.stop()

        assert len(player.audio) == 2
        assert player.audio[0] == generate_button_cue_wav(pressed=True)
        assert player.audio[0] != player.audio[1]
        assert player.cancel_count == 2

    asyncio.run(scenario())


def test_each_interaction_starts_with_the_next_machine_loop() -> None:
    async def scenario() -> None:
        player = RecordingCancellablePlayer()
        controller = ThinkingAudioController(
            player=player,
            clip_seconds=1.0,
            clip_count=3,
            seed=11,
        )

        await controller.prepare()
        for _ in range(3):
            await controller.start()
            await asyncio.sleep(0)
            await controller.stop()

        assert len(player.audio) == 3
        assert len(set(player.audio)) == 3

    asyncio.run(scenario())
