from __future__ import annotations

import argparse
import asyncio
import logging
from collections.abc import Sequence
from pathlib import Path

from desk_pet.config import AppConfig, ConfigError, load_config
from desk_pet.events import Event, EventBus, EventType
from desk_pet.hardware.desktop.keyboard_trigger import KeyboardTrigger
from desk_pet.hardware.desktop.simulated_face import TerminalFace
from desk_pet.hardware.interfaces import FaceDevice, TriggerDevice
from desk_pet.state_machine import PetState, StateMachine

LOGGER = logging.getLogger(__name__)


class DeskPetApplication:
    def __init__(
        self,
        trigger: TriggerDevice,
        face: FaceDevice,
        events: EventBus | None = None,
    ) -> None:
        self.events = events or EventBus()
        self.state = StateMachine(self.events)
        self.trigger = trigger
        self.face = face
        self.events.subscribe(self._display_state)

    async def _display_state(self, event: Event) -> None:
        if event.type is EventType.STATE_CHANGED:
            await self.face.set_state(str(event.payload["state"]))

    async def run(self) -> None:
        await self.state.transition_to(PetState.IDLE)
        while True:
            action = await self.trigger.wait_for_trigger()
            await self.events.emit(Event.create(EventType.TRIGGER_RECEIVED, action=action))
            if action == "exit":
                return
            if action == "listen":
                await self.state.transition_to(PetState.LISTENING)
                await asyncio.sleep(0.35)
                await self.state.transition_to(PetState.IDLE)


def build_application(config: AppConfig) -> DeskPetApplication:
    if config.trigger.driver != "keyboard":
        raise ConfigError(f"Unsupported Stage 1 trigger driver: {config.trigger.driver}")
    if config.face.driver != "terminal":
        raise ConfigError(f"Unsupported Stage 1 face driver: {config.face.driver}")
    return DeskPetApplication(KeyboardTrigger(), TerminalFace())


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Portable AI desk pet")
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("configs/windows.yaml"),
        help="Path to a YAML configuration file",
    )
    return parser.parse_args(argv)


async def async_main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        config = load_config(args.config)
        app = build_application(config)
        print(f"Desk Pet Stage 1 ({config.profile})")
        print("Press Space to simulate listening. Press Escape to exit.")
        await app.run()
        print("Desk Pet stopped cleanly.")
        return 0
    except (ConfigError, RuntimeError) as exc:
        LOGGER.error("%s", exc)
        return 2


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    raise SystemExit(asyncio.run(async_main()))


if __name__ == "__main__":
    main()
