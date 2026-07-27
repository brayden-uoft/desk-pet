import asyncio
from dataclasses import dataclass
from typing import Any

from desk_pet.audio.openai_services import OpenAISpeechSynthesizer, OpenAITranscriptionService


@dataclass
class FakeTranscriptionResult:
    text: str


class FakeTranscriptionsAPI:
    def __init__(self) -> None:
        self.arguments: dict[str, Any] = {}

    async def create(self, **arguments: Any) -> FakeTranscriptionResult:
        self.arguments = arguments
        return FakeTranscriptionResult("  hello from audio  ")


class FakeSpeechResponse:
    async def aread(self) -> bytes:
        return b"wav-speech"


class FakeSpeechAPI:
    def __init__(self) -> None:
        self.arguments: dict[str, Any] = {}

    async def create(self, **arguments: Any) -> FakeSpeechResponse:
        self.arguments = arguments
        return FakeSpeechResponse()


def test_transcription_uses_in_memory_wav() -> None:
    async def scenario() -> None:
        api = FakeTranscriptionsAPI()
        service = OpenAITranscriptionService(
            model="test-transcribe",
            request_timeout_seconds=1,
            transcriptions=api,
        )

        assert await service.transcribe(b"wav-bytes") == "hello from audio"
        assert api.arguments == {
            "model": "test-transcribe",
            "file": ("utterance.wav", b"wav-bytes", "audio/wav"),
        }

    asyncio.run(scenario())


def test_speech_requests_wav_without_a_temporary_file() -> None:
    async def scenario() -> None:
        api = FakeSpeechAPI()
        service = OpenAISpeechSynthesizer(
            model="test-speech",
            voice="test-voice",
            speed=1.5,
            request_timeout_seconds=1,
            speech=api,
        )

        assert await service.synthesize("hello") == b"wav-speech"
        assert api.arguments == {
            "model": "test-speech",
            "voice": "test-voice",
            "input": "hello",
            "response_format": "wav",
            "speed": 1.5,
        }

    asyncio.run(scenario())
