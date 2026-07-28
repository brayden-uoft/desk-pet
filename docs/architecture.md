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
Right Alt down -> LISTENING -> Right Alt up -> TRANSCRIBING -> THINKING
      -> optional USING_TOOL -> SPEAKING -> IDLE
Escape during LISTENING or SPEAKING -> cancel operation -> IDLE
Escape while IDLE -> clean shutdown
```

Windows recording and playback use `sounddevice` adapters. Recording,
transcription, speech synthesis, and playback are separate interfaces, so
tests replace all four without opening a physical device or contacting an API.
The application transfers WAV bytes in memory instead of persisting temporary
media.

Windows voice mode globally polls the physical right Alt key state. A down edge starts the
microphone and an up edge requests a graceful stop, preserving the captured
audio for transcription. Escape uses the separate cancellation signal and
discards active recording or playback. Idle Escape presses are ignored in the
packaged Windows application so background use is not interrupted; Ctrl+C or
closing the terminal shuts it down.

The keyboard adapter polls for keys asynchronously. This lets cancellation
stop waiting cleanly without leaving a blocked background thread that could
consume a later right Alt or Escape press.

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

## Stage 6 web search

The OpenAI model client can attach the hosted `web_search` tool to Responses
API requests. The model decides when current information needs a search and
returns its final answer in the same response. This hosted tool is deliberately
separate from the local skill registry: it cannot run shell commands, read
local files, or fetch an arbitrary caller-supplied URL.

Search can be disabled per deployment profile, and its context size is
restricted to `low`, `medium`, or `high` by configuration validation. The
existing five-iteration limit still governs local function tools.

## Stage 7A approved runtime context

DeskBob's public-safe persona and Brayden's private profile are separate
Markdown documents with YAML front matter. Only documents explicitly marked
`status: approved` are loaded. The persona is required; the private profile is
optional so a clean clone still starts without personal data.

The private profile lives below the git-ignored `data/` directory. At startup,
both approved documents are read under a combined character limit and encoded
as JSON context inside the model instructions. Context is personalization
data—it cannot override safety rules or tool permissions. Edits take effect
after restarting the application.

This stage provides approved identity continuity, not learned memory. Durable
remember, inspect, correct, forget, and personality-evolution services remain
separate later stages.

## Desktop face preview

The hardware-independent face model produces animated binary matrices with
exactly 16 rows and 32 columns. A value is either on or off; the preview maps on
to red and off to near-black. There is no RGB state in the model.

The Windows adapter renders those frames in a dedicated Tk process while
retaining terminal state output. Using a separate process keeps Tk on its own
main thread and prevents the UI event loop from blocking asyncio, microphone
capture, model calls, or playback. Closing the preview window does not stop
DeskBob; exiting DeskBob closes the preview process.

## Non-blocking thinking audio

Voice mode procedurally generates four mechanical clips in memory during
application startup. It also prepares distinct push-to-talk press and release
cues. On push-to-talk release, the acknowledgement and first robot-brain loop
start before transcription, then varied loops continue concurrently through
transcription, model/tool work, and final-answer synthesis:

```text
Right Alt down -> press cue -> record
Right Alt up -> release cue + machine loop -> transcribe -> model/tools
             -> synthesize answer -> stop loop -> SPEAKING -> play answer
```

The final response pipeline never awaits completion of a machine loop. It only
signals cancellation before answer playback, bounded by the player's short
audio block. No interaction sound is written to disk or fetched from a
third-party asset.
