from __future__ import annotations

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
    ) -> _SpeechResponse: ...


class OpenAITranscriptionService:
    def __init__(
        self,
        *,
        model: str,
        request_timeout_seconds: float,
        transcriptions: _TranscriptionsAPI | None = None,
    ) -> None:
        if transcriptions is None:
            sdk = AsyncOpenAI(timeout=request_timeout_seconds, max_retries=1)
            transcriptions = cast(_TranscriptionsAPI, sdk.audio.transcriptions)
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
        request_timeout_seconds: float,
        speech: _SpeechAPI | None = None,
    ) -> None:
        if speech is None:
            sdk = AsyncOpenAI(timeout=request_timeout_seconds, max_retries=1)
            speech = cast(_SpeechAPI, sdk.audio.speech)
        self._speech = speech
        self._model = model
        self._voice = voice

    async def synthesize(self, text: str) -> bytes:
        try:
            response = await self._speech.create(
                model=self._model,
                voice=self._voice,
                input=text,
                response_format="wav",
            )
            return await response.aread()
        except Exception as exc:
            raise AudioError("I couldn't generate speech for that response.") from exc
