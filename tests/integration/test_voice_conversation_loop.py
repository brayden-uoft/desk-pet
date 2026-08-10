import asyncio
from pathlib import Path

from desk_pet.audio.errors import AudioCancelled
from desk_pet.conversation import ConversationService
from desk_pet.hardware.interfaces import CancellationToken
from desk_pet.latency import VoiceLatencySample
from desk_pet.main import BRIEFING_PROMPT, VISUAL_PROMPT, DeskPetApplication
from desk_pet.memory.conversation_store import ConversationStore
from tests.fakes.agent import FakeModelClient
from tests.fakes.hardware import (
    CancellablePlayer,
    CancellableRecorder,
    FakeFace,
    FakeOutputControl,
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
        latencies: list[VoiceLatencySample] = []
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
            latency_observer=latencies.append,
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
        assert len(latencies) == 1
        latency = latencies[0]
        assert latency.recording_seconds >= 0
        assert latency.release_to_transcript_seconds >= 0
        assert latency.release_to_response_seconds >= latency.release_to_transcript_seconds
        assert latency.release_to_audio_seconds >= latency.release_to_response_seconds
        assert latency.playback_seconds >= 0
        assert latency.total_turn_seconds >= latency.release_to_audio_seconds

    asyncio.run(scenario())


def test_briefing_visual_privacy_and_output_controls(tmp_path: Path) -> None:
    async def scenario() -> None:
        trigger = QueueTrigger()
        face = FakeFace()
        output: list[str] = []
        output_control = FakeOutputControl()
        model = FakeModelClient(["Briefing ready.", "I see a desk."])
        app = DeskPetApplication(
            trigger,
            face,
            conversation=ConversationService(
                model=model,
                store=ConversationStore(tmp_path / "controls.db"),
                history_limit=8,
                request_timeout_seconds=1,
            ),
            output=output.append,
            output_control=output_control,
        )

        run_task = asyncio.create_task(app.run())
        await trigger.send("briefing")
        await _wait_for_state_count(face, 4)
        await trigger.send("visual")
        await _wait_for_state_count(face, 7)
        await trigger.send("volume_up")
        while not any(state.startswith("volume:") for state in face.states):
            await asyncio.sleep(0)
        await trigger.send("mute_toggle")
        await _wait_for_state(face, "muted")
        await trigger.send("privacy_toggle")
        await _wait_for_state(face, "sleeping")
        request_count = len(model.requests)
        await trigger.send("visual")
        await asyncio.sleep(0.01)
        await trigger.send("privacy_toggle")
        await _wait_for_state(face, "muted")
        await trigger.send("exit")
        await run_task

        assert model.requests[0][-1].content == BRIEFING_PROMPT
        assert model.requests[1][-1].content == VISUAL_PROMPT
        assert len(model.requests) == request_count
        assert round(output_control.volume, 1) == 0.8
        assert output_control.muted
        assert "DeskBob> Privacy sleep enabled." in output

    asyncio.run(scenario())


def test_rapid_dial_burst_always_restores_face() -> None:
    async def scenario() -> None:
        trigger = QueueTrigger()
        face = FakeFace()
        output_control = FakeOutputControl()
        app = DeskPetApplication(
            trigger,
            face,
            output_control=output_control,
            volume_overlay_seconds=0.01,
        )

        run_task = asyncio.create_task(app.run())
        burst = ["volume_down"] * 5 + ["volume_up"] * 20 + ["volume_down"] * 5
        for action in burst:
            await trigger.send(action)
        while len([state for state in face.states if state.startswith("volume:")]) < len(burst):
            await asyncio.sleep(0)
        await asyncio.sleep(0.03)

        assert face.states[-1] == "idle"
        assert round(output_control.volume, 1) == 0.5

        await trigger.send("exit")
        await run_task

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


def test_muted_voice_turn_skips_paid_speech_synthesis(tmp_path: Path) -> None:
    async def scenario() -> None:
        trigger = QueueTrigger()
        recorder = PushToTalkRecorder()
        synthesizer = FakeSynthesizer()
        output_control = FakeOutputControl()
        output: list[str] = []
        output_control.set_muted(True)
        app = DeskPetApplication(
            trigger,
            FakeFace(),
            conversation=ConversationService(
                model=FakeModelClient(["Text-only while muted."]),
                store=ConversationStore(tmp_path / "muted.db"),
                history_limit=8,
                request_timeout_seconds=1,
            ),
            interaction_mode="voice",
            recorder=recorder,
            transcriber=FakeTranscriber("Question"),
            synthesizer=synthesizer,
            player=FakePlayer(),
            output_control=output_control,
            output=output.append,
        )

        run_task = asyncio.create_task(app.run())
        await trigger.send("listen_start")
        await recorder.started.wait()
        await trigger.send("listen_stop")
        while "DeskBob> Text-only while muted." not in output:
            await asyncio.sleep(0)
        await trigger.send("exit")
        await run_task

        assert synthesizer.texts == []

    asyncio.run(scenario())


def test_voice_keeps_citations_on_screen_but_does_not_speak_urls(tmp_path: Path) -> None:
    async def scenario() -> None:
        trigger = QueueTrigger()
        face = FakeFace()
        recorder = PushToTalkRecorder()
        synthesizer = FakeSynthesizer()
        output: list[str] = []
        cited_answer = (
            "Rain is likely. ([Toronto forecast](https://weather.example/toronto/hourly))"
        )
        app = DeskPetApplication(
            trigger,
            face,
            conversation=ConversationService(
                model=FakeModelClient([cited_answer]),
                store=ConversationStore(tmp_path / "citations.db"),
                history_limit=20,
                request_timeout_seconds=1,
            ),
            output=output.append,
            interaction_mode="voice",
            recorder=recorder,
            transcriber=FakeTranscriber("Will it rain?"),
            synthesizer=synthesizer,
            player=FakePlayer(),
        )

        run_task = asyncio.create_task(app.run())
        await trigger.send("listen_start")
        await recorder.started.wait()
        await trigger.send("listen_stop")
        await _wait_for_state_count(face, 6)
        await trigger.send("exit")
        await run_task

        assert synthesizer.texts == ["Rain is likely."]
        assert output[-1] == f"DeskBob> {cited_answer}"

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


def test_a_interrupts_speech_and_immediately_starts_a_new_recording(tmp_path: Path) -> None:
    async def scenario() -> None:
        class RestartableRecorder:
            def __init__(self) -> None:
                self.calls = 0

            async def record_utterance(self, cancellation: CancellationToken) -> bytes:
                self.calls += 1
                while not cancellation.stop_requested:
                    if cancellation.cancelled:
                        raise AudioCancelled("Recording cancelled.")
                    await asyncio.sleep(0)
                return b"fake-wav"

        class InterruptibleThenFastPlayer:
            def __init__(self) -> None:
                self.calls = 0
                self.first_started = asyncio.Event()
                self.first_interrupted = False

            async def play(self, audio: bytes, cancellation: CancellationToken) -> None:
                del audio
                self.calls += 1
                if self.calls > 1:
                    return
                self.first_started.set()
                while not cancellation.cancelled:
                    await asyncio.sleep(0)
                self.first_interrupted = True
                raise AudioCancelled("Playback cancelled.")

        trigger = QueueTrigger()
        recorder = RestartableRecorder()
        player = InterruptibleThenFastPlayer()
        face = FakeFace()
        app = DeskPetApplication(
            trigger,
            face,
            conversation=ConversationService(
                model=FakeModelClient(["First answer.", "Second answer."]),
                store=ConversationStore(tmp_path / "interrupt.db"),
                history_limit=8,
                request_timeout_seconds=1,
            ),
            interaction_mode="voice",
            recorder=recorder,
            transcriber=FakeTranscriber("Question"),
            synthesizer=FakeSynthesizer(),
            player=player,
        )

        run_task = asyncio.create_task(app.run())
        await trigger.send("listen_start")
        while recorder.calls < 1:
            await asyncio.sleep(0)
        await trigger.send("listen_stop")
        await player.first_started.wait()
        await trigger.send("listen_start")
        while recorder.calls < 2:
            await asyncio.sleep(0)
        await trigger.send("listen_stop")
        while player.calls < 2:
            await asyncio.sleep(0)
        await _wait_for_state_count(face, 11)
        await trigger.send("exit")
        await run_task

        assert player.first_interrupted
        assert recorder.calls == 2

    asyncio.run(scenario())
