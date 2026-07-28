from __future__ import annotations

import argparse
import asyncio
from collections.abc import Sequence
from contextlib import suppress

from desk_pet.hardware.desktop.preview_face import DesktopPreviewFace

DEMO_STATES = (
    "idle",
    "listening",
    "transcribing",
    "thinking",
    "using_tool",
    "speaking",
    "error",
)


async def _run_demo(*, cycles: int, state_seconds: float) -> None:
    face = DesktopPreviewFace()
    completed_cycles = 0
    try:
        while cycles == 0 or completed_cycles < cycles:
            for state in DEMO_STATES:
                await face.set_state(state)
                display_seconds = state_seconds
                if state == "idle":
                    display_seconds = max(display_seconds, 7.0)
                elif state == "speaking":
                    display_seconds = max(display_seconds, 2.5)
                await asyncio.sleep(display_seconds)
            completed_cycles += 1
    finally:
        await face.close()


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Preview DeskBob's 32x16 red LED face")
    parser.add_argument(
        "--cycles",
        type=int,
        default=0,
        help="Number of full state cycles; 0 repeats until Ctrl+C",
    )
    parser.add_argument(
        "--state-seconds",
        type=float,
        default=1.2,
        help="Seconds to show each state",
    )
    args = parser.parse_args(argv)
    with suppress(KeyboardInterrupt):
        asyncio.run(_run_demo(cycles=max(0, args.cycles), state_seconds=args.state_seconds))


if __name__ == "__main__":
    main()
