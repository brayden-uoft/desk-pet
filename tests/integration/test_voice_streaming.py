import asyncio
from collections.abc import AsyncIterator, Callable
from pathlib import Path

from desk_pet.conversation import ConversationService
from desk_pet.hardware.interfaces import CancellationToken
from desk_pet.latency import VoiceLatencySample
from desk_pet.main import DeskPetApplication
from desk_pet.memory.conversation_store import ConversationStore
from tests.fakes.agent import FakeModelClient
from tests.fakes.hardware import FakeFace, FakeTranscriber, PushToTalkRecorder, QueueTrigger


class FakeStreamingSynthesizer:
    def __init__(self) -> None:
        self.texts: list[str] = []

    async def synthesize(self, text: str) -> bytes:
        raise AssertionError(f"Legacy synthesis used for {text}")

    async def synthesize_pcm_stream(self, text: str) -> AsyncIterator[bytes]:
        self.texts.append(text)
        for chunk in (b"pcm-one", b"pcm-two"):
            yield chunk


class FakeStreamingPlayer:
    def __init__(self) -> None:
        self.chunks: list[bytes] = []

    async def play(self, audio: bytes, cancellation: CancellationToken) -> None:
        raise AssertionError(f"Legacy playback used for {audio!r}")

    async def play_pcm_stream(
        self,
        chunks: AsyncIterator[bytes],
        cancellation: CancellationToken,
        on_audio_started: Callable[[], None],
    ) -> None:
        started = False
        async for chunk in chunks:
            assert not cancellation.cancelled
            if not started:
                started = True
                on_audio_started()
            self.chunks.append(chunk)


def test_voice_turn_streams_pcm_instead_of_waiting_for_complete_wav(tmp_path: Path) -> None:
    async def scenario() -> None:
        trigger = QueueTrigger()
        recorder = PushToTalkRecorder()
        synthesizer = FakeStreamingSynthesizer()
        player = FakeStreamingPlayer()
        latencies: list[VoiceLatencySample] = []
        app = DeskPetApplication(
            trigger,
            FakeFace(),
            conversation=ConversationService(
                model=FakeModelClient(["Hello, Brayden!"]),
                store=ConversationStore(tmp_path / "streaming.db"),
                history_limit=8,
                request_timeout_seconds=1,
            ),
            interaction_mode="voice",
            recorder=recorder,
            transcriber=FakeTranscriber("Say hello."),
            synthesizer=synthesizer,
            player=player,
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

        assert synthesizer.texts == ["Hello, Brayden!"]
        assert player.chunks == [b"pcm-one", b"pcm-two"]
        assert latencies[0].synthesis_seconds >= 0

    asyncio.run(scenario())
