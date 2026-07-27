import asyncio

from desk_pet.audio.thinking import ThinkingAudioController
from tests.fakes.hardware import CancellablePlayer, FakeSynthesizer


def test_thinking_audio_is_preloaded_then_stops_cleanly() -> None:
    async def scenario() -> None:
        synthesizer = FakeSynthesizer(audio=b"thinking-wav")
        player = CancellablePlayer()
        controller = ThinkingAudioController(
            synthesizer=synthesizer,
            player=player,
            phrase="Uhh... processing...",
        )

        await controller.prepare()
        await controller.start()
        await player.started.wait()
        await controller.stop()

        assert synthesizer.texts == ["Uhh... processing..."]
        assert player.cancelled

    asyncio.run(scenario())
