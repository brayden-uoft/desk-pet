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

## Stage 2 flow

```text
STARTING -> IDLE
Space -> LISTENING -> typed input -> THINKING -> SPEAKING -> IDLE
Escape -> clean shutdown
```

The application builds model input from recent SQLite conversation turns and
the new user message. The model client uses the OpenAI Responses API with
remote response storage disabled because SQLite is the local source of truth.
Audio will replace only the typed-input boundary in a later stage.
