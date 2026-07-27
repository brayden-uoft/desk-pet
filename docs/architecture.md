# Architecture

Desk Pet is one application with replaceable hardware adapters.

```text
Application
  state machine -> conversation -> controlled agent loop
       |
       +-- TriggerDevice
       +-- FaceDevice
       +-- AudioRecorder
       +-- TranscriptionService
       +-- SpeechSynthesizer
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
Audio and vision extend the input boundary without changing conversation
storage.

## Stage 3 tool loop

```text
model response
  -> final text: return it
  -> function call:
       validate registered name and JSON arguments
       reject duplicate calls
       execute one approved skill
       append function_call_output with the original call_id
       ask the model again
```

Parallel tool calls are disabled. The loop executes no more than five tool
requests and exposes no shell, filesystem, email, or calendar actions.

## Stage 4 voice flow

```text
STARTING -> IDLE
Space -> LISTENING -> TRANSCRIBING -> THINKING
      -> optional USING_TOOL -> SPEAKING -> IDLE
Escape during LISTENING or SPEAKING -> cancel operation -> IDLE
Escape while IDLE -> clean shutdown
```

Windows recording and playback use `sounddevice` adapters. Recording,
transcription, speech synthesis, and playback are separate interfaces, so
tests replace all four without opening a physical device or contacting an API.
The application transfers WAV bytes in memory instead of persisting temporary
media.

The keyboard adapter polls for keys asynchronously. This lets cancellation
stop waiting cleanly without leaving a blocked background thread that could
consume a later Space or Escape press.

## Stage 5 vision flow

```text
visual question -> model requests capture_camera_image -> USING_TOOL
  -> OpenCV opens configured camera -> reads one frame -> releases camera
  -> resize -> JPEG encode in memory
  -> function_call_output containing JSON status + input_image
  -> model answers from image -> SPEAKING -> IDLE
```

The camera adapter calls `read()` exactly once per approved tool execution and
releases the device in a guaranteed cleanup block. It performs no background
capture. The JPEG is represented as an in-memory data URL only for the current
Responses API tool loop; SQLite stores the user and assistant text, not the
image.
