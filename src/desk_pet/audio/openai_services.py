from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, Protocol, cast

from openai import AsyncOpenAI

from desk_pet.audio.errors import AudioError


class _TranscriptionResult(Protocol):
    text: str


class _TranscriptionsAPI(Protocol):
    async def create(self, *, model: str, file: Any) -> _TranscriptionResult: ...


class _SpeechResponse(Protocol):
    async def aread(self) -> bytes: ...


class _SpeechAPI(Protocol):
    async def create(
        self,
        *,
        model: str,
        voice: str,
        input: str,
        response_format: str,
        speed: float,
    ) -> _SpeechResponse: ...

    @property
    def with_streaming_response(self) -> Any: ...


class OpenAITranscriptionService:
    def __init__(
        self,
        *,
        model: str,
        request_timeout_seconds: float,
        sdk: AsyncOpenAI | None = None,
        transcriptions: _TranscriptionsAPI | None = None,
    ) -> None:
        if transcriptions is None:
            client = sdk or AsyncOpenAI(timeout=request_timeout_seconds, max_retries=1)
            transcriptions = cast(_TranscriptionsAPI, client.audio.transcriptions)
        self._transcriptions = transcriptions
        self._model = model

    async def transcribe(self, audio: bytes) -> str:
        try:
            result = await self._transcriptions.create(
                model=self._model,
                file=("utterance.wav", audio, "audio/wav"),
            )
        except Exception as exc:
            raise AudioError("I couldn't transcribe that recording.") from exc
        return result.text.strip()


class OpenAISpeechSynthesizer:
    def __init__(
        self,
        *,
        model: str,
        voice: str,
        speed: float,
        request_timeout_seconds: float,
        sdk: AsyncOpenAI | None = None,
        speech: _SpeechAPI | None = None,
    ) -> None:
        if speech is None:
            client = sdk or AsyncOpenAI(timeout=request_timeout_seconds, max_retries=1)
            speech = cast(_SpeechAPI, client.audio.speech)
        self._speech = speech
        self._model = model
        self._voice = voice
        self._speed = speed

    async def synthesize(self, text: str) -> bytes:
        try:
            response = await self._speech.create(
                model=self._model,
                voice=self._voice,
                input=text,
                response_format="wav",
                speed=self._speed,
            )
            return await response.aread()
        except Exception as exc:
            raise AudioError("I couldn't generate speech for that response.") from exc

    async def synthesize_pcm_stream(self, text: str) -> AsyncIterator[bytes]:
        try:
            async with self._speech.with_streaming_response.create(
                model=self._model,
                voice=self._voice,
                input=text,
                response_format="pcm",
                speed=self._speed,
            ) as response:
                async for chunk in response.iter_bytes(chunk_size=4_800):
                    if chunk:
                        yield chunk
        except Exception as exc:
            raise AudioError("I couldn't stream speech for that response.") from exc
