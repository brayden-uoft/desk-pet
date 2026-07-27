from __future__ import annotations

import asyncio
import logging
import multiprocessing
import queue
from typing import Any

from desk_pet.face.frames import FACE_HEIGHT, FACE_WIDTH, frames_for_state
from desk_pet.hardware.desktop.simulated_face import TerminalFace

LOGGER = logging.getLogger(__name__)
RED_ON = "#ff2020"
RED_OFF = "#170303"
GRID_COLOR = "#360808"


def _run_preview_window(
    states: Any,
    pixel_size: int,
    frame_interval_ms: int,
) -> None:
    try:
        import tkinter as tk

        root = tk.Tk()
        root.title("DeskBob Face — 32x16 monochrome red preview")
        root.configure(bg="#090000")
        root.resizable(False, False)
        canvas = tk.Canvas(
            root,
            width=FACE_WIDTH * pixel_size,
            height=FACE_HEIGHT * pixel_size,
            bg="#090000",
            highlightthickness=0,
        )
        canvas.pack(padx=14, pady=(14, 8))
        pixels: list[list[Any]] = []
        for y in range(FACE_HEIGHT):
            row: list[Any] = []
            for x in range(FACE_WIDTH):
                pad = 2
                row.append(
                    canvas.create_rectangle(
                        x * pixel_size + pad,
                        y * pixel_size + pad,
                        (x + 1) * pixel_size - pad,
                        (y + 1) * pixel_size - pad,
                        fill=RED_OFF,
                        outline=GRID_COLOR,
                    )
                )
            pixels.append(row)

        state_label = tk.Label(
            root,
            text="IDLE  •  32 × 16  •  RED / OFF",
            bg="#090000",
            fg=RED_ON,
            font=("Consolas", 12, "bold"),
        )
        state_label.pack(pady=(0, 12))
        current_state = "idle"
        frame_index = 0

        def draw_next_frame() -> None:
            nonlocal current_state, frame_index
            while True:
                try:
                    update = states.get_nowait()
                except queue.Empty:
                    break
                if update is None:
                    root.destroy()
                    return
                current_state = update
                frame_index = 0

            frames = frames_for_state(current_state)
            frame = frames[frame_index % len(frames)]
            frame_index += 1
            for y, row in enumerate(frame):
                for x, value in enumerate(row):
                    canvas.itemconfigure(pixels[y][x], fill=RED_ON if value else RED_OFF)
            state_label.configure(text=f"{current_state.upper()}  •  32 × 16  •  RED / OFF")
            root.after(frame_interval_ms, draw_next_frame)

        root.protocol("WM_DELETE_WINDOW", root.destroy)
        draw_next_frame()
        root.mainloop()
    except Exception:
        LOGGER.exception("DeskBob face preview window stopped")


class DesktopPreviewFace:
    """Terminal state output plus a live monochrome-red 32x16 Tk preview."""

    def __init__(self, *, pixel_size: int = 20, frame_interval_ms: int = 140) -> None:
        self._terminal = TerminalFace()
        context = multiprocessing.get_context("spawn")
        self._states = context.Queue()
        self._process = context.Process(
            target=_run_preview_window,
            args=(self._states, pixel_size, frame_interval_ms),
            name="deskbob-face-preview",
            daemon=True,
        )
        self._process.start()

    async def set_state(self, state: str) -> None:
        await self._terminal.set_state(state)
        if self._process.is_alive():
            self._states.put(state)

    async def close(self) -> None:
        if not self._process.is_alive():
            return
        self._states.put(None)
        await asyncio.to_thread(self._process.join, 2.0)
