# Desk Pet

A portable Python application for an AI desk pet. Development starts with
deterministic laptop simulations; physical KICKPI K2B hardware will be added
through replaceable adapters.

## Stage 4: laptop voice

Requirements:

- Windows 10 or 11
- Python 3.11 or newer
- A microphone and speakers or headphones

Launch in voice mode from PowerShell:

```powershell
.\scripts\run_windows.ps1 -Mode voice
```

Create your local environment file once:

```powershell
Copy-Item .env.example .env
notepad .env
```

Replace `your-api-key-here` with an OpenAI API key. Never commit `.env`.

The first launch creates `.venv` and installs the project. When the idle face
appears, tap `Space` and speak. Recording stops after 1.2 seconds of silence or
the 15-second hard timeout. Press `Escape` to interrupt recording or playback.
Press `Escape` while idle to exit.

Typed input remains available:

```powershell
.\scripts\run_windows.ps1 -Mode text
```

To inspect the Windows audio devices and the current defaults:

```powershell
.\.venv\Scripts\python.exe -m sounddevice
```

Set `audio.input_device` or `audio.output_device` in `configs/windows.yaml` to
an index from that list when the system default is not the device you want.

Run the validation suite:

```powershell
.\scripts\test.ps1
```

Conversation turns are stored in `data/desk_pet.db`. Tests use fake model,
recording, transcription, speech, and playback services. They never make
network calls and require no physical audio devices.

Audio is passed between components as in-memory WAV bytes. The normal voice
path does not create temporary recordings or speech files.

Stage 3 exposes exactly three approved tools:

- `get_current_time`
- `start_timer`
- `capture_camera_image` (an intentional stub until Stage 5)

The tool loop validates arguments, rejects duplicate calls, disables parallel
tool calls, and stops after five tool iterations.

## Development stages

1. Repository foundation and terminal hardware simulator
2. Text-only AI conversation
3. Safe skill and tool loop
4. Laptop audio
5. Webcam vision
6. K2B preparation and physical-driver integration

See [architecture](docs/architecture.md), [deployment](docs/deployment.md), and
[safety](docs/safety.md) for design constraints.
