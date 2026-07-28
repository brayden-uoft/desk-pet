import asyncio
from pathlib import Path

from desk_pet.conversation import ConversationService
from desk_pet.hardware.interfaces import CancellationToken
from desk_pet.main import DeskPetApplication
from desk_pet.memory.conversation_store import ConversationStore
from tests.fakes.agent import FakeModelClient
from tests.fakes.hardware import (
    CancellablePlayer,
    CancellableRecorder,
    FakeFace,
    FakePlayer,
    FakeRecorder,
    FakeSynthesizer,
    FakeThinkingAudio,
    FakeTranscriber,
    PushToTalkRecorder,
    QueueTrigger,
)


async def _wait_for_state(face: FakeFace, state: str) -> None:
    for _ in range(200):
        if face.states and face.states[-1] == state:
            return
        await asyncio.sleep(0.01)
    raise AssertionError(f"State {state!r} was not reached; saw {face.states!r}")


async def _wait_for_state_count(face: FakeFace, count: int) -> None:
    for _ in range(200):
        if len(face.states) >= count:
            return
        await asyncio.sleep(0.01)
    raise AssertionError(f"Expected {count} states; saw {face.states!r}")


def test_voice_question_produces_spoken_response_without_hardware(tmp_path: Path) -> None:
    async def scenario() -> None:
        trigger = QueueTrigger()
        face = FakeFace()
        output: list[str] = []
        recorder = PushToTalkRecorder()
        transcriber = FakeTranscriber("Where do pandas live?")
        synthesizer = FakeSynthesizer()
        player = FakePlayer()
        thinking_audio = FakeThinkingAudio()
        conversation = ConversationService(
            model=FakeModelClient(["Pandas live in China."]),
            store=ConversationStore(tmp_path / "desk_pet.db"),
            history_limit=20,
            request_timeout_seconds=1,
        )
        app = DeskPetApplication(
            trigger,
            face,
            conversation=conversation,
            output=output.append,
            interaction_mode="voice",
            recorder=recorder,
            transcriber=transcriber,
            synthesizer=synthesizer,
            player=player,
            thinking_audio=thinking_audio,
        )

        run_task = asyncio.create_task(app.run())
        await trigger.send("listen_start")
        await recorder.started.wait()
        await trigger.send("listen_stop")
        await _wait_for_state_count(face, 6)
        await trigger.send("exit")
        await run_task

        assert face.states == [
            "idle",
            "listening",
            "transcribing",
            "thinking",
            "speaking",
            "idle",
        ]
        assert recorder.stopped
        assert transcriber.recordings == [b"fake-wav"]
        assert synthesizer.texts == ["Pandas live in China."]
        assert player.audio == [b"fake-speech-wav"]
        assert thinking_audio.prepared
        assert thinking_audio.listen_started_count == 1
        assert thinking_audio.start_count == 1
        assert thinking_audio.stop_count == 1
        assert output == [
            "You> Where do pandas live?",
            "DeskBob> Pandas live in China.",
        ]
        assert not list(tmp_path.glob("*.wav"))
        assert not list(tmp_path.glob("*.mp3"))

    asyncio.run(scenario())


def test_thinking_audio_does_not_block_response_work(tmp_path: Path) -> None:
    async def scenario() -> None:
        events: list[str] = []
        trigger = QueueTrigger()
        face = FakeFace()
        recorder = PushToTalkRecorder()

        class OrderedThinkingAudio:
            async def prepare(self) -> None:
                events.append("prepare")

            async def listen_started(self) -> None:
                events.append("listen_cue")

            async def start(self) -> None:
                events.append("filler_start")

            async def stop(self) -> None:
                events.append("filler_stop")

        class OrderedTranscriber:
            async def transcribe(self, audio: bytes) -> str:
                events.append("transcribe")
                return "Question"

        class OrderedSynthesizer:
            async def synthesize(self, text: str) -> bytes:
                events.append("synthesize_answer")
                return b"answer-wav"

        class OrderedPlayer:
            async def play(self, audio: bytes, cancellation: CancellationToken) -> None:
                events.append("play_answer")

        app = DeskPetApplication(
            trigger,
            face,
            conversation=ConversationService(
                model=FakeModelClient(["Answer"]),
                store=ConversationStore(tmp_path / "ordered.db"),
                history_limit=20,
                request_timeout_seconds=1,
            ),
            interaction_mode="voice",
            recorder=recorder,
            transcriber=OrderedTranscriber(),
            synthesizer=OrderedSynthesizer(),
            player=OrderedPlayer(),
            thinking_audio=OrderedThinkingAudio(),
        )

        run_task = asyncio.create_task(app.run())
        await trigger.send("listen_start")
        await recorder.started.wait()
        await trigger.send("listen_stop")
        await _wait_for_state_count(face, 6)
        await trigger.send("exit")
        await run_task

        assert events == [
            "prepare",
            "listen_cue",
            "filler_start",
            "transcribe",
            "synthesize_answer",
            "filler_stop",
            "play_answer",
        ]

    asyncio.run(scenario())


def test_escape_cancels_recording_and_returns_to_idle(tmp_path: Path) -> None:
    async def scenario() -> None:
        trigger = QueueTrigger()
        face = FakeFace()
        recorder = CancellableRecorder()
        app = DeskPetApplication(
            trigger,
            face,
            conversation=ConversationService(
                model=FakeModelClient(["unused"]),
                store=ConversationStore(tmp_path / "desk_pet.db"),
                history_limit=20,
                request_timeout_seconds=1,
            ),
            interaction_mode="voice",
            recorder=recorder,
            transcriber=FakeTranscriber("unused"),
            synthesizer=FakeSynthesizer(),
            player=FakePlayer(),
        )

        run_task = asyncio.create_task(app.run())
        await trigger.send("listen")
        await recorder.started.wait()
        await trigger.send("exit")
        await _wait_for_state(face, "idle")
        await trigger.send("exit")
        await run_task

        assert face.states == ["idle", "listening", "idle"]

    asyncio.run(scenario())


def test_escape_cancels_playback_and_returns_to_idle(tmp_path: Path) -> None:
    async def scenario() -> None:
        trigger = QueueTrigger()
        face = FakeFace()
        player = CancellablePlayer()
        app = DeskPetApplication(
            trigger,
            face,
            conversation=ConversationService(
                model=FakeModelClient(["A spoken answer."]),
                store=ConversationStore(tmp_path / "desk_pet.db"),
                history_limit=20,
                request_timeout_seconds=1,
            ),
            interaction_mode="voice",
            recorder=FakeRecorder(),
            transcriber=FakeTranscriber("A question"),
            synthesizer=FakeSynthesizer(),
            player=player,
        )

        run_task = asyncio.create_task(app.run())
        await trigger.send("listen")
        await player.started.wait()
        await trigger.send("exit")
        await _wait_for_state(face, "idle")
        await trigger.send("exit")
        await run_task

        assert player.cancelled
        assert face.states[-2:] == ["speaking", "idle"]

    asyncio.run(scenario())
