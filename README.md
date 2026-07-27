# Desk Pet

A portable Python application for an AI desk pet. Development starts with
deterministic laptop simulations; physical KICKPI K2B hardware will be added
through replaceable adapters.

## Stage 3: approved skills

Requirements:

- Windows 10 or 11
- Python 3.11 or newer

Launch from PowerShell:

```powershell
.\scripts\run_windows.ps1
```

Create your local environment file once:

```powershell
Copy-Item .env.example .env
notepad .env
```

Replace `your-api-key-here` with an OpenAI API key. Never commit `.env`.

The first launch creates `.venv` and installs the project. When the idle face
appears, tap `Space`, type a message, and press `Enter`. Tap `Space` again for
the next turn. Press `Escape` while idle to exit.

Run the validation suite:

```powershell
.\scripts\test.ps1
```

Conversation turns are stored in `data/desk_pet.db`. Tests use a fake model and
never make network calls.

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
