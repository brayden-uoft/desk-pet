# Deployment

## Windows development

From PowerShell:

```powershell
.\scripts\run_windows.ps1 -Mode text
.\scripts\run_windows.ps1 -Mode voice
```

List available microphone and playback devices:

```powershell
.\.venv\Scripts\python.exe -m sounddevice
```

## KICKPI K2B

K2B deployment begins only after the laptop interaction loop is stable. The
planned native Python setup is:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install .
python -m desk_pet --config configs/kickpi.yaml
```

Do not use Docker initially. Native access is simpler for USB audio, camera,
Bluetooth keyboard input, SPI, and GPIO.
