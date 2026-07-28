# Desk Pet

A portable Python application for an AI desk pet. Development starts with
deterministic laptop simulations; physical KICKPI K2B hardware will be added
through replaceable adapters.

## Stage 6: laptop voice, vision, and live web search

Requirements:

- Windows 10 or 11
- Python 3.11 or newer
- A microphone and speakers or headphones
- A webcam

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
appears, hold the **right Alt key** while speaking and release it to send.
Transcription starts as soon as the key is released. Right Alt is polled as a
global Windows key, so the terminal can be minimized and another application
can have focus. The 15-second hard timeout remains as a safety limit. Press
`Escape` to interrupt recording or playback. When DeskBob is idle, global
Escape presses are ignored so another application cannot accidentally shut him
down. Press `Ctrl+C` in PowerShell or close the terminal window to exit.

The Windows profile opens a live DeskBob face window driven by the same state
events as the eventual hardware. It is exactly 32 pixels wide by 16 pixels
tall, and every pixel is binary: red or off. To preview all expressions without
starting the AI or using an API key:

```powershell
.\scripts\preview_face.ps1
```

DeskBob plays a short rising chirp when right Alt is pressed and a falling
acknowledgement when it is released. While transcription, model work, tools,
and final speech synthesis continue concurrently, a locally generated robot
brain soundscape fills the dead air with a low cog-like whirr, relay clicks,
and irregular electronic beeps. Four different loops are generated in memory
at startup, require no API call or downloaded audio, and stop immediately
before the real answer plays. Disable all interaction sounds with
`audio.thinking_audio_enabled` in `configs/windows.yaml`; adjust
`audio.thinking_volume` to make them quieter or louder.

Preview the exact interaction sound design without an API call:

```powershell
.\scripts\preview_sounds.ps1
```

The passive face now holds still for a randomized few seconds between small
behaviors instead of blinking once per second. It occasionally blinks, looks
left or right, smirks, licks its lips, or sticks out its tongue. During spoken
answers, the eyes remain stable while the mouth moves gradually through
neighboring shapes at a calmer cadence.

Ask a visual question such as `What am I holding?` to let the model request
one webcam frame. The terminal enters `USING_TOOL`, OpenCV captures and
JPEG-compresses exactly one frame, and the model's answer is spoken. The camera
is not opened for ordinary questions and there is no continuous recording.

Ask for current information such as `What's the weather in Toronto?` and the
model can use OpenAI's hosted, read-only web search before answering. Search is
enabled in `configs/windows.yaml`; `web_search_context_size` controls how much
search context is used. This does not allow arbitrary local commands or expose
a general-purpose URL-fetching tool.

DeskBob's approved personality lives in `configs/persona.md`. A private,
approved user profile can live at `data/private/user-profile.md`; the entire
`data/` directory is excluded from Git, so personal context is never pushed to
the public repository. Both documents require `status: approved` in YAML front
matter before they are loaded. Draft or missing user profiles are ignored.
Restart DeskBob after editing either context document.

Windows voice output uses the `echo` voice at `1.5x` speed by default. Override
the voice with `OPENAI_SPEECH_VOICE` or edit `audio.speech_speed` in
`configs/windows.yaml`.

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
Set `camera.index` in the same file if the intended webcam is not index `0`.

Run the validation suite:

```powershell
.\scripts\test.ps1
```

Conversation turns are stored in `data/desk_pet.db`. Tests use fake model,
recording, transcription, speech, and playback services. They never make
network calls and require no physical audio or camera devices.

Audio is passed between components as in-memory WAV bytes. The normal voice
path does not create temporary recordings or speech files. Camera frames are
passed as in-memory JPEG data and are not saved to disk.

Stage 3 exposes exactly three approved tools:

- `get_current_time`
- `start_timer`
- `capture_camera_image`

The tool loop validates arguments, rejects duplicate calls, disables parallel
tool calls, and stops after five tool iterations.

## Development stages

1. Repository foundation and terminal hardware simulator
2. Text-only AI conversation
3. Safe skill and tool loop
4. Laptop audio
5. Webcam vision
6. Read-only hosted web search
7. Approved private profile and DeskBob personality
8. Durable memory and evolving personality
9. External connectors and approval-gated actions
10. K2B preparation and physical-driver integration

See [architecture](docs/architecture.md), [deployment](docs/deployment.md), and
[safety](docs/safety.md) for design constraints.
