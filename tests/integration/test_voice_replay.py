import asyncio
from pathlib import Path

import pytest

from desk_pet.conversation import ConversationService
from desk_pet.hardware.desktop.simulated_face import TerminalFace
from desk_pet.latency import VoiceLatencySample
from desk_pet.main import DeskPetApplication
from desk_pet.memory.conversation_store import ConversationStore
from desk_pet.voice_replay import VoiceReplayController
from tests.fakes.agent import FakeModelClient
from tests.fakes.hardware import FakePlayer, FakeSynthesizer, FakeTranscriber


def test_private_audio_replay_drives_complete_voice_turns_without_microphone(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        controller = VoiceReplayController(b"private-recorded-wav", summary_interval=2)
        transcriber = FakeTranscriber("Say hello in one sentence.")
        synthesizer = FakeSynthesizer()
        player = FakePlayer()
        samples: list[VoiceLatencySample] = []

        def observe(sample: VoiceLatencySample) -> None:
            samples.append(sample)
            controller.observe(sample)

        app = DeskPetApplication(
            controller.trigger,
            TerminalFace(output=lambda _line: None),
            conversation=ConversationService(
                model=FakeModelClient(["Hello!", "Hello again!"]),
                store=ConversationStore(tmp_path / "replay.db"),
                history_limit=8,
                request_timeout_seconds=1,
            ),
            interaction_mode="voice",
            recorder=controller.recorder,
            transcriber=transcriber,
            synthesizer=synthesizer,
            player=player,
            latency_observer=observe,
        )

        await controller.run(app, turns=2)

        assert transcriber.recordings == [b"private-recorded-wav"] * 2
        assert synthesizer.texts == ["Hello!", "Hello again!"]
        assert player.audio == [b"fake-speech-wav"] * 2
        assert len(samples) == 2

    asyncio.run(scenario())


def test_private_audio_replay_times_out_instead_of_hanging(tmp_path: Path) -> None:
    async def scenario() -> None:
        controller = VoiceReplayController(b"private-recorded-wav", summary_interval=1)
        app = DeskPetApplication(
            controller.trigger,
            TerminalFace(output=lambda _line: None),
            conversation=ConversationService(
                model=FakeModelClient(["unused"]),
                store=ConversationStore(tmp_path / "timeout.db"),
                history_limit=8,
                request_timeout_seconds=1,
            ),
            interaction_mode="voice",
            recorder=controller.recorder,
            transcriber=FakeTranscriber(""),
            synthesizer=FakeSynthesizer(),
            player=FakePlayer(),
            latency_observer=controller.observe,
        )

        with pytest.raises(RuntimeError, match="did not complete"):
            await controller.run(app, turns=1, turn_timeout_seconds=0.01)

    asyncio.run(scenario())
