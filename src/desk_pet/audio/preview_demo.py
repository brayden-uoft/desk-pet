from __future__ import annotations

import asyncio
from contextlib import suppress

from desk_pet.audio.errors import AudioCancelled
from desk_pet.audio.thinking import (
    generate_button_cue_wav,
    generate_mechanical_thinking_wav,
)
from desk_pet.hardware.desktop.sounddevice_audio import SoundDevicePlayer
from desk_pet.hardware.interfaces import CancellationToken


async def _run_demo() -> None:
    player = SoundDevicePlayer()
    cancellation = CancellationToken()
    print("Right Alt down: recording-engaged cue")
    await player.play(generate_button_cue_wav(pressed=True), cancellation)
    await asyncio.sleep(0.25)
    print("Right Alt up: acknowledgement + robot-brain machinery")
    await player.play(
        generate_mechanical_thinking_wav(
            duration_seconds=5.0,
            seed=None,
            release_cue=True,
        ),
        cancellation,
    )


def main() -> None:
    with suppress(KeyboardInterrupt, AudioCancelled):
        asyncio.run(_run_demo())


if __name__ == "__main__":
    main()
