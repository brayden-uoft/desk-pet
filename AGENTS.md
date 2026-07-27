# Project rules

- Python 3.11+.
- Code must run on Windows and Linux ARM64.
- Core logic must not import platform-specific hardware libraries.
- All hardware uses interfaces in `hardware/interfaces.py`.
- Every new feature requires tests.
- Use async APIs for audio, model requests and hardware events.
- Do not expose unrestricted shell execution.
- Do not commit secrets or generated media.
- Run formatting, type checking and tests before finishing.

