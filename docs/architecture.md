# Architecture

Desk Pet is one application with replaceable hardware adapters.

```text
Application
  state machine -> conversation -> controlled agent loop
       |
       +-- TriggerDevice
       +-- FaceDevice
       +-- AudioRecorder
       +-- AudioPlayer
       +-- CameraDevice
```

Core application modules must not directly import Windows keyboard APIs, Linux
GPIO, OpenCV, ALSA, or MAX7219 libraries. Those dependencies belong in adapter
packages under `hardware/`.

Every state transition emits a `STATE_CHANGED` event. Future conversation,
tool, and response events use the same event model.

## Stage 1 flow

```text
STARTING -> IDLE
Space -> LISTENING -> IDLE
Escape -> clean shutdown
```

The temporary return from `LISTENING` to `IDLE` is a seam for Stage 2 and Stage
4. It proves input and display wiring without pretending audio exists.

