import asyncio

from desk_pet.main import DeskPetApplication
from tests.fakes.hardware import FakeFace, FakeTrigger


def test_listen_cycle_returns_to_idle_and_exits() -> None:
    async def scenario() -> None:
        face = FakeFace()
        app = DeskPetApplication(FakeTrigger(["listen", "exit"]), face)

        await app.run()

        assert face.states == ["idle", "listening", "idle"]
        assert app.state.state == "idle"

    asyncio.run(scenario())


def test_background_mode_ignores_idle_escape() -> None:
    async def scenario() -> None:
        face = FakeFace()
        app = DeskPetApplication(
            FakeTrigger(["exit", "shutdown"]),
            face,
            exit_on_idle_cancel=False,
        )

        await app.run()

        assert face.states == ["idle"]

    asyncio.run(scenario())
