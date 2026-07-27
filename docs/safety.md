# Safety

- Never commit API keys or user recordings.
- Never expose unrestricted shell execution as an agent tool.
- Keep physical hardware access behind narrow interfaces.
- Require explicit confirmation for externally consequential actions.
- Bound every external call with timeouts and retry limits.
- On an unrecoverable interaction error, show `ERROR` and return to `IDLE`.
- Store only conversation history during the MVP.

