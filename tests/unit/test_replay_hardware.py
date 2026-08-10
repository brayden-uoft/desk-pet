import asyncio

import pytest

from desk_pet.audio.errors import AudioCancelled
from desk_pet.hardware.interfaces import CancellationToken
from desk_pet.hardware.replay import QueuedTrigger, ReplayAudioRecorder


def test_queued_trigger_delivers_scripted_action() -> None:
    async def scenario() -> None:
        trigger = QueuedTrigger()
        await trigger.send("listen_start")
        assert await trigger.wait_for_trigger() == "listen_start"

    asyncio.run(scenario())


def test_replay_recorder_returns_private_wav_after_release() -> None:
    async def scenario() -> None:
        recorder = ReplayAudioRecorder(b"private-wav")
        cancellation = CancellationToken()
        task = asyncio.create_task(recorder.record_utterance(cancellation))

        assert await recorder.wait_until_started() == 1
        cancellation.request_stop()

        assert await task == b"private-wav"

    asyncio.run(scenario())


def test_replay_recorder_honors_cancellation() -> None:
    async def scenario() -> None:
        recorder = ReplayAudioRecorder(b"private-wav")
        cancellation = CancellationToken()
        task = asyncio.create_task(recorder.record_utterance(cancellation))
        await recorder.wait_until_started()
        cancellation.cancel()

        with pytest.raises(AudioCancelled, match="cancelled"):
            await task

    asyncio.run(scenario())


def test_replay_recorder_rejects_empty_audio() -> None:
    with pytest.raises(ValueError, match="must not be empty"):
        ReplayAudioRecorder(b"")
