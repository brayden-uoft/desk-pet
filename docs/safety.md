# Safety

- Never commit API keys or user recordings.
- Keep microphone audio and synthesized speech in memory; delete any future
  diagnostic media in guaranteed cleanup blocks.
- Record only after an explicit Space press and stop on silence, timeout, or
  Escape.
- Open the webcam only after an approved `capture_camera_image` tool request,
  read one frame, release it immediately, and keep the JPEG in memory.
- Never expose unrestricted shell execution as an agent tool.
- Keep physical hardware access behind narrow interfaces.
- Require explicit confirmation for externally consequential actions.
- Bound every external call with timeouts and retry limits.
- On an unrecoverable interaction error, show `ERROR` and return to `IDLE`.
- Store only conversation history during the MVP.
