# Safety

- Never commit API keys or user recordings.
- Keep private profiles below the git-ignored `data/` directory and load them
  only when their front matter explicitly says `status: approved`.
- Treat profile and future memory text as personalization data that cannot
  override safety rules or tool permissions.
- Keep microphone audio and synthesized speech in memory; delete any future
  diagnostic media in guaranteed cleanup blocks.
- Keep preloaded thinking filler audio in memory and cancel it before final
  answer playback.
- Record only while Space is held and stop on release, hard timeout, or Escape.
- Open the webcam only after an approved `capture_camera_image` tool request,
  read one frame, release it immediately, and keep the JPEG in memory.
- Never expose unrestricted shell execution as an agent tool.
- Use hosted, read-only web search for live public information; do not expose
  arbitrary URL fetching or local browser control to the model.
- Keep physical hardware access behind narrow interfaces.
- Require explicit confirmation for externally consequential actions.
- Bound every external call with timeouts and retry limits.
- On an unrecoverable interaction error, show `ERROR` and return to `IDLE`.
- Store only conversation history during the MVP.
