# Desk Pet

A portable Python application for an AI desk pet. Development starts with
deterministic laptop simulations; physical KICKPI K2B hardware will be added
through replaceable adapters.

## Stage 1: laptop simulator

Requirements:

- Windows 10 or 11
- Python 3.11 or newer

Launch from PowerShell:

```powershell
.\scripts\run_windows.ps1
```

The first launch creates `.venv` and installs the project. When the idle face
appears, press `Space` to simulate a listening cycle. Press `Escape` to exit.

Run the validation suite:

```powershell
.\scripts\test.ps1
```

Stage 1 intentionally has no AI, audio, camera, or external API calls.

## Development stages

1. Repository foundation and terminal hardware simulator
2. Text-only AI conversation
3. Safe skill and tool loop
4. Laptop audio
5. Webcam vision
6. K2B preparation and physical-driver integration

See [architecture](docs/architecture.md), [deployment](docs/deployment.md), and
[safety](docs/safety.md) for design constraints.

