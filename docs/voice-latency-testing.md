# Voice latency testing

DeskBob supports a private, reusable Windows voice fixture. The fixture lets the complete
transcription, model, speech-generation, playback, and latency-reporting path run without
requiring a new microphone recording for every test.

## Record the fixture once

```powershell
.\scripts\record_voice_fixture.ps1
```

Say `Say hello in one sentence.` and press Enter after speaking. The WAV is saved under
`data/private/voice-fixtures/`, which is excluded from Git.

## Replay the live pipeline

```powershell
.\scripts\test_voice_replay.ps1
```

This submits the saved WAV directly to DeskBob and plays the synthesized response. It uses
the real configured API services, so it is a live smoke test rather than a unit test and may
incur normal API usage. Use `-Turns 5` to produce the rolling p50/p95 summary.

The normal test suite uses fake audio, transcription, model, synthesis, and playback services.
It requires no microphone, speaker, network connection, API key, or private fixture.

## Benchmark the sub-second voice lane

Voice mode defaults to a persistent Realtime speech-to-speech session. Ordinary conversation
stays on that connection; requests needing web search, current information, connected accounts,
camera, timers, or durable memory delegate to the full tool-capable agent automatically.

```powershell
.\scripts\test_realtime_replay.ps1 -Turns 10 -NoPlayback
```

Remove `-NoPlayback` to hear each response. Both forms measure release-to-first-audio-byte.
Set `OPENAI_REALTIME_ENABLED=false` in `.env` to force the standard STT + Responses + TTS lane.

The August 9, 2026 Windows fixture confirmation measured 797 ms p50, 1,141 ms p95, and
749 ms best over ten turns. Live network conditions will vary.
