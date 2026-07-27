from __future__ import annotations

import argparse
import asyncio
import logging
import os
from collections.abc import Callable, Sequence
from pathlib import Path

from dotenv import load_dotenv

from desk_pet.agent.client import OpenAIModelClient
from desk_pet.agent.loop import AgentLoop
from desk_pet.config import AppConfig, ConfigError, load_config
from desk_pet.conversation import ConversationError, ConversationService
from desk_pet.events import Event, EventBus, EventType
from desk_pet.hardware.desktop.keyboard_trigger import KeyboardTrigger
from desk_pet.hardware.desktop.simulated_face import TerminalFace
from desk_pet.hardware.interfaces import FaceDevice, TriggerDevice
from desk_pet.memory.conversation_store import ConversationStore
from desk_pet.skills.defaults import create_default_skill_registry
from desk_pet.state_machine import PetState, StateMachine

LOGGER = logging.getLogger(__name__)


class DeskPetApplication:
    def __init__(
        self,
        trigger: TriggerDevice,
        face: FaceDevice,
        conversation: ConversationService | None = None,
        events: EventBus | None = None,
        text_input: Callable[[str], str] = input,
        output: Callable[[str], None] = print,
    ) -> None:
        self.events = events or EventBus()
        self.state = StateMachine(self.events)
        self.trigger = trigger
        self.face = face
        self.conversation = conversation
        self.text_input = text_input
        self.output = output
        self.events.subscribe(self._display_state)
        self.events.subscribe(self._handle_tool_request)

    async def _display_state(self, event: Event) -> None:
        if event.type is EventType.STATE_CHANGED:
            await self.face.set_state(str(event.payload["state"]))

    async def _handle_tool_request(self, event: Event) -> None:
        if event.type is EventType.TOOL_REQUESTED:
            await self.state.transition_to(PetState.USING_TOOL)

    async def run(self) -> None:
        if self.conversation is not None:
            await self.conversation.initialize()
        await self.state.transition_to(PetState.IDLE)
        while True:
            action = await self.trigger.wait_for_trigger()
            await self.events.emit(Event.create(EventType.TRIGGER_RECEIVED, action=action))
            if action == "exit":
                return
            if action == "listen":
                await self._handle_listen()

    async def _handle_listen(self) -> None:
        await self.state.transition_to(PetState.LISTENING)
        if self.conversation is None:
            await asyncio.sleep(0.35)
            await self.state.transition_to(PetState.IDLE)
            return

        user_text = (await asyncio.to_thread(self.text_input, "You> ")).strip()
        if not user_text:
            self.output("Type a message after pressing Space.")
            await self.state.transition_to(PetState.IDLE)
            return

        await self.events.emit(Event.create(EventType.TRANSCRIPT_READY, text=user_text))
        await self.state.transition_to(PetState.THINKING)
        try:
            assistant_text = await self.conversation.reply(user_text)
        except ConversationError as exc:
            await self.state.transition_to(PetState.ERROR)
            self.output(f"Desk Pet> {exc}")
            await self.state.transition_to(PetState.IDLE)
            return

        await self.events.emit(Event.create(EventType.RESPONSE_READY, text=assistant_text))
        await self.state.transition_to(PetState.SPEAKING)
        self.output(f"Desk Pet> {assistant_text}")
        await self.state.transition_to(PetState.IDLE)


def build_application(config: AppConfig) -> DeskPetApplication:
    if config.trigger.driver != "keyboard":
        raise ConfigError(f"Unsupported Stage 1 trigger driver: {config.trigger.driver}")
    if config.face.driver != "terminal":
        raise ConfigError(f"Unsupported Stage 2 face driver: {config.face.driver}")
    if config.agent.provider != "openai":
        raise ConfigError(f"Unsupported model provider: {config.agent.provider}")
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key or api_key == "your-api-key-here":
        raise ConfigError("OPENAI_API_KEY is missing. Copy .env.example to .env and add your key.")

    response_model = OpenAIModelClient(
        model=config.agent.model,
        reasoning_effort=config.agent.reasoning_effort,
        request_timeout_seconds=config.agent.request_timeout_seconds,
        maximum_output_tokens=config.agent.maximum_output_tokens,
    )
    events = EventBus()

    async def on_tool_requested(name: str) -> None:
        await events.emit(Event.create(EventType.TOOL_REQUESTED, name=name))

    model = AgentLoop(
        model=response_model,
        skills=create_default_skill_registry(),
        maximum_tool_iterations=config.agent.maximum_tool_iterations,
        on_tool_requested=on_tool_requested,
    )
    store = ConversationStore(config.storage.database_path)
    conversation = ConversationService(
        model=model,
        store=store,
        history_limit=config.agent.history_limit,
        request_timeout_seconds=config.agent.request_timeout_seconds,
    )
    return DeskPetApplication(
        KeyboardTrigger(),
        TerminalFace(),
        conversation=conversation,
        events=events,
    )


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
        load_dotenv()
        config = load_config(args.config)
        app = build_application(config)
        print(f"Desk Pet Stage 2 ({config.profile}, {config.agent.model})")
        print("Tap Space, type a message, and press Enter. Press Escape while idle to exit.")
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
