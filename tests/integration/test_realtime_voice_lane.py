from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from pathlib import Path

from desk_pet.audio.realtime import RealtimeVoiceResult
from desk_pet.conversation import ConversationService
from desk_pet.hardware.interfaces import CancellationToken
from desk_pet.latency import VoiceLatencySample
from desk_pet.main import DeskPetApplication
from desk_pet.memory.conversation_store import ConversationStore
from tests.fakes.agent import FakeModelClient
from tests.fakes.hardware import (
    FakeFace,
    FakePlayer,
    FakeSynthesizer,
    FakeTranscriber,
    PushToTalkRecorder,
    QueueTrigger,
)


class FakeRealtimeVoice:
    def __init__(self, result: RealtimeVoiceResult) -> None:
        self.result = result
        self.started = False
        self.closed = False
        self.recordings: list[bytes] = []

    async def start(self) -> None:
        self.started = True

    async def close(self) -> None:
        self.closed = True

    async def respond(
        self,
        recording: bytes,
        cancellation: CancellationToken,
        on_audio_started: Callable[[], None],
    ) -> RealtimeVoiceResult:
        assert not cancellation.cancelled
        self.recordings.append(recording)
        on_audio_started()
        return self.result


class FakeStreamingRecorder:
    def __init__(self) -> None:
        self.started = asyncio.Event()

    async def record_utterance(self, cancellation: CancellationToken) -> bytes:
        raise AssertionError("Buffered recording path used")

    async def record_utterance_stream(
        self,
        cancellation: CancellationToken,
        on_pcm_chunk: Callable[[bytes], Awaitable[None]],
    ) -> bytes:
        self.started.set()
        await on_pcm_chunk(b"pcm-24khz")
        while not cancellation.stop_requested:
            await asyncio.sleep(0)
        return b"fallback-wav"


class FakeStreamingRealtime(FakeRealtimeVoice):
    def __init__(self, result: RealtimeVoiceResult) -> None:
        super().__init__(result)
        self.began = False
        self.chunks: list[bytes] = []
        self.streamed_responses = 0

    async def begin_audio_input(self) -> None:
        self.began = True

    async def append_audio_input(self, pcm_24khz: bytes) -> None:
        self.chunks.append(pcm_24khz)

    async def cancel_audio_input(self) -> None:
        self.began = False

    async def respond_to_streamed_audio(
        self,
        cancellation: CancellationToken,
        on_audio_started: Callable[[], None],
    ) -> RealtimeVoiceResult:
        self.streamed_responses += 1
        on_audio_started()
        return self.result


def test_voice_turn_uses_realtime_lane_and_persists_transcripts(tmp_path: Path) -> None:
    async def scenario() -> None:
        trigger = QueueTrigger()
        recorder = PushToTalkRecorder()
        store = ConversationStore(tmp_path / "realtime.db")
        realtime = FakeRealtimeVoice(
            RealtimeVoiceResult(
                user_transcript="Say hello.",
                assistant_transcript="Hello, Brayden!",
            )
        )
        output: list[str] = []
        latencies: list[VoiceLatencySample] = []
        app = DeskPetApplication(
            trigger,
            FakeFace(),
            conversation=ConversationService(
                model=FakeModelClient(["standard lane must not run"]),
                store=store,
                history_limit=8,
                request_timeout_seconds=1,
            ),
            interaction_mode="voice",
            recorder=recorder,
            transcriber=FakeTranscriber("standard lane must not transcribe"),
            synthesizer=FakeSynthesizer(),
            player=FakePlayer(),
            output=output.append,
            realtime_voice=realtime,
            latency_observer=latencies.append,
        )

        run_task = asyncio.create_task(app.run())
        await trigger.send("listen_start")
        await recorder.started.wait()
        await trigger.send("listen_stop")
        while not latencies:
            await asyncio.sleep(0)
        await trigger.send("shutdown")
        await run_task

        assert realtime.started and realtime.closed
        assert realtime.recordings
        assert "You> Say hello." in output
        assert "DeskBob> Hello, Brayden!" in output
        turns = await store.recent(1)
        assert turns[0].user_text == "Say hello."
        assert turns[0].assistant_text == "Hello, Brayden!"
        assert latencies[0].release_to_audio_seconds >= 0

    asyncio.run(scenario())


def test_realtime_delegation_runs_full_agent_lane(tmp_path: Path) -> None:
    async def scenario() -> None:
        trigger = QueueTrigger()
        recorder = PushToTalkRecorder()
        realtime = FakeRealtimeVoice(
            RealtimeVoiceResult(
                user_transcript="What's the weather?",
                assistant_transcript="",
                delegated_request="What's the current weather in Toronto?",
            )
        )
        output: list[str] = []
        app = DeskPetApplication(
            trigger,
            FakeFace(),
            conversation=ConversationService(
                model=FakeModelClient(["Toronto is sunny."]),
                store=ConversationStore(tmp_path / "delegated.db"),
                history_limit=8,
                request_timeout_seconds=1,
            ),
            interaction_mode="voice",
            recorder=recorder,
            transcriber=FakeTranscriber("unused"),
            synthesizer=FakeSynthesizer(),
            player=FakePlayer(),
            output=output.append,
            realtime_voice=realtime,
        )

        run_task = asyncio.create_task(app.run())
        await trigger.send("listen_start")
        await recorder.started.wait()
        await trigger.send("listen_stop")
        while "DeskBob> Toronto is sunny." not in output:
            await asyncio.sleep(0)
        await trigger.send("shutdown")
        await run_task

        assert "You> What's the weather?" in output
        assert "DeskBob> Toronto is sunny." in output

    asyncio.run(scenario())


def test_microphone_pcm_streams_during_push_to_talk(tmp_path: Path) -> None:
    async def scenario() -> None:
        trigger = QueueTrigger()
        recorder = FakeStreamingRecorder()
        realtime = FakeStreamingRealtime(
            RealtimeVoiceResult("Hello.", "Hi!"),
        )
        output: list[str] = []
        app = DeskPetApplication(
            trigger,
            FakeFace(),
            conversation=ConversationService(
                model=FakeModelClient(["unused"]),
                store=ConversationStore(tmp_path / "stream-input.db"),
                history_limit=8,
                request_timeout_seconds=1,
            ),
            interaction_mode="voice",
            recorder=recorder,
            transcriber=FakeTranscriber("unused"),
            synthesizer=FakeSynthesizer(),
            player=FakePlayer(),
            output=output.append,
            realtime_voice=realtime,
        )

        run_task = asyncio.create_task(app.run())
        await trigger.send("listen_start")
        await recorder.started.wait()
        while not realtime.chunks:
            await asyncio.sleep(0)
        await trigger.send("listen_stop")
        while "DeskBob> Hi!" not in output:
            await asyncio.sleep(0)
        await trigger.send("shutdown")
        await run_task

        assert realtime.began
        assert realtime.chunks == [b"pcm-24khz"]
        assert realtime.streamed_responses == 1
        assert realtime.recordings == []

    asyncio.run(scenario())
