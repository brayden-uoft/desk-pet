from __future__ import annotations

import argparse
import asyncio
import os
import subprocess
import sys
import time
from collections.abc import Iterator, Sequence
from contextlib import AbstractContextManager, contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol

from desk_pet.integrations.interfaces import (
    OutlookCalendarEvent,
    OutlookMailMessage,
    OutlookStatus,
)

OUTLOOK_INBOX_FOLDER = 6
OUTLOOK_CALENDAR_FOLDER = 9
MAIL_SCAN_LIMIT_PER_STORE = 50
BODY_EXCERPT_CHARACTERS = 1200


class OutlookClassicError(RuntimeError):
    """The local Outlook profile could not be read safely."""


class NamespaceContextFactory(Protocol):
    def __call__(self) -> AbstractContextManager[Any]: ...


class WindowsOutlookClassicService:
    """Read Outlook Classic through an existing local MAPI profile."""

    def __init__(
        self,
        namespace_factory: NamespaceContextFactory | None = None,
    ) -> None:
        self._namespace_factory = namespace_factory or _windows_outlook_namespace

    async def status(self) -> OutlookStatus:
        return await asyncio.to_thread(self._status_sync)

    async def search_mail(
        self,
        query: str,
        *,
        maximum_results: int,
        include_body: bool,
    ) -> list[OutlookMailMessage]:
        return await asyncio.to_thread(
            self._search_mail_sync,
            query,
            maximum_results,
            include_body,
        )

    async def calendar_events(
        self,
        start: datetime,
        end: datetime,
        *,
        maximum_results: int,
    ) -> list[OutlookCalendarEvent]:
        return await asyncio.to_thread(
            self._calendar_events_sync,
            start,
            end,
            maximum_results,
        )

    def _status_sync(self) -> OutlookStatus:
        try:
            with self._namespace_factory() as namespace:
                stores = _store_names(namespace)
                try:
                    profile_name = _string_attribute(namespace.CurrentUser, "Name")
                except Exception:
                    # Some valid profiles, especially Exchange/public-folder profiles,
                    # abort the optional CurrentUser lookup while their stores remain usable.
                    profile_name = ""
        except Exception as exc:
            return OutlookStatus(
                available=False,
                profile_name="",
                stores=[],
                message=_safe_outlook_error(exc),
            )
        if not stores:
            return OutlookStatus(
                available=False,
                profile_name=profile_name,
                stores=[],
                message="Outlook Classic opened, but no signed-in mailbox stores were found.",
            )
        return OutlookStatus(
            available=True,
            profile_name=profile_name,
            stores=stores,
            message="Outlook Classic is available locally. No Azure or OAuth app is required.",
        )

    def _search_mail_sync(
        self,
        query: str,
        maximum_results: int,
        include_body: bool,
    ) -> list[OutlookMailMessage]:
        normalized_query = query.casefold().strip()
        matches: list[OutlookMailMessage] = []
        try:
            with self._namespace_factory() as namespace:
                stores = list(_iter_collection(namespace.Stores))
                for store in stores:
                    account = _string_attribute(store, "DisplayName") or "Outlook"
                    if account.casefold().startswith("public folders"):
                        continue
                    try:
                        folder = store.GetDefaultFolder(OUTLOOK_INBOX_FOLDER)
                        items = folder.Items
                        items.Sort("[ReceivedTime]", True)
                    except Exception:
                        continue
                    scan_count = min(_collection_count(items), MAIL_SCAN_LIMIT_PER_STORE)
                    for index in range(1, scan_count + 1):
                        try:
                            item = items.Item(index)
                            subject = _string_attribute(item, "Subject")
                            sender_name = _string_attribute(item, "SenderName")
                            sender_address = _string_attribute(item, "SenderEmailAddress")
                            headers = f"{subject}\n{sender_name}\n{sender_address}".casefold()
                            body = ""
                            if include_body or (
                                normalized_query and normalized_query not in headers
                            ):
                                body = _string_attribute(item, "Body")
                            if (
                                normalized_query
                                and normalized_query not in headers
                                and normalized_query not in body.casefold()
                            ):
                                continue
                            matches.append(
                                OutlookMailMessage(
                                    account=account,
                                    subject=subject or "(no subject)",
                                    sender_name=sender_name,
                                    sender_address=sender_address,
                                    received_at=_iso_attribute(item, "ReceivedTime"),
                                    body_excerpt=(
                                        _compact_excerpt(body, BODY_EXCERPT_CHARACTERS)
                                        if include_body
                                        else None
                                    ),
                                )
                            )
                        except Exception:
                            continue
        except Exception as exc:
            raise OutlookClassicError(_safe_outlook_error(exc)) from exc
        matches.sort(key=lambda message: message["received_at"], reverse=True)
        return matches[:maximum_results]

    def _calendar_events_sync(
        self,
        start: datetime,
        end: datetime,
        maximum_results: int,
    ) -> list[OutlookCalendarEvent]:
        events: list[OutlookCalendarEvent] = []
        local_start = start.astimezone()
        local_end = end.astimezone()
        restriction = (
            f"[Start] >= '{local_start.strftime('%m/%d/%Y %I:%M %p')}' "
            f"AND [Start] < '{local_end.strftime('%m/%d/%Y %I:%M %p')}'"
        )
        try:
            with self._namespace_factory() as namespace:
                stores = list(_iter_collection(namespace.Stores))
                for store in stores:
                    account = _string_attribute(store, "DisplayName") or "Outlook"
                    if account.casefold().startswith("public folders"):
                        continue
                    try:
                        folder = store.GetDefaultFolder(OUTLOOK_CALENDAR_FOLDER)
                        items = folder.Items
                        items.Sort("[Start]")
                        items.IncludeRecurrences = True
                        items = items.Restrict(restriction)
                    except Exception:
                        continue
                    item_count = min(
                        _collection_count(items),
                        max(maximum_results * 3, maximum_results),
                    )
                    for index in range(1, item_count + 1):
                        try:
                            item = items.Item(index)
                            events.append(
                                OutlookCalendarEvent(
                                    account=account,
                                    subject=_string_attribute(item, "Subject")
                                    or "(untitled event)",
                                    start=_iso_attribute(item, "Start"),
                                    end=_iso_attribute(item, "End"),
                                    location=_string_attribute(item, "Location"),
                                    organizer=_string_attribute(item, "Organizer"),
                                    all_day=bool(getattr(item, "AllDayEvent", False)),
                                )
                            )
                        except Exception:
                            continue
        except Exception as exc:
            raise OutlookClassicError(_safe_outlook_error(exc)) from exc
        events.sort(key=lambda event: event["start"])
        return events[:maximum_results]


def outlook_classic_installed() -> bool:
    if sys.platform != "win32":
        return False
    return any(path.is_file() for path in _outlook_executable_candidates())


def _outlook_executable_candidates() -> tuple[Path, ...]:
    program_files = Path(os.environ.get("PROGRAMFILES", r"C:\Program Files"))
    program_files_x86 = Path(os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)"))
    return (
        program_files / "Microsoft Office" / "root" / "Office16" / "OUTLOOK.EXE",
        program_files_x86 / "Microsoft Office" / "root" / "Office16" / "OUTLOOK.EXE",
    )


@contextmanager
def _windows_outlook_namespace() -> Iterator[Any]:
    if sys.platform != "win32":
        raise OutlookClassicError("Outlook Classic local access is available only on Windows.")
    try:
        import pythoncom  # type: ignore[import-untyped]
        import win32com.client  # type: ignore[import-untyped]
    except ImportError as exc:
        raise OutlookClassicError(
            "The Windows Outlook adapter is not installed. Rerun the connector wizard."
        ) from exc
    pythoncom.CoInitialize()
    try:
        application = _get_or_start_outlook_application(win32com.client)
        yield application.GetNamespace("MAPI")
    finally:
        pythoncom.CoUninitialize()


def _get_or_start_outlook_application(client: Any) -> Any:
    try:
        return client.GetActiveObject("Outlook.Application")
    except Exception:
        executable = next(
            (path for path in _outlook_executable_candidates() if path.is_file()),
            None,
        )
        if executable is None:
            return client.Dispatch("Outlook.Application")
        startup_info = subprocess.STARTUPINFO()
        startup_info.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startup_info.wShowWindow = 6  # SW_MINIMIZE
        subprocess.Popen(  # noqa: S603
            [str(executable), "/recycle"],
            startupinfo=startup_info,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        for _ in range(20):
            try:
                return client.GetActiveObject("Outlook.Application")
            except Exception:
                time.sleep(0.25)
        return client.Dispatch("Outlook.Application")


def _iter_collection(collection: Any) -> Iterator[Any]:
    for index in range(1, _collection_count(collection) + 1):
        yield collection.Item(index)


def _collection_count(collection: Any) -> int:
    value = getattr(collection, "Count", 0)
    return int(value) if isinstance(value, (int, float)) else 0


def _store_names(namespace: Any) -> list[str]:
    names = []
    for store in _iter_collection(namespace.Stores):
        name = _string_attribute(store, "DisplayName")
        if name:
            names.append(name)
    return names


def _string_attribute(value: Any, name: str) -> str:
    result = getattr(value, name, "")
    return str(result).strip() if result is not None else ""


def _iso_attribute(value: Any, name: str) -> str:
    result = getattr(value, name, None)
    if isinstance(result, datetime):
        return result.isoformat()
    return str(result).strip() if result is not None else ""


def _compact_excerpt(value: str, maximum_characters: int) -> str:
    compact = " ".join(value.split())
    if len(compact) <= maximum_characters:
        return compact
    return f"{compact[: maximum_characters - 3].rstrip()}..."


def _safe_outlook_error(exc: Exception) -> str:
    if isinstance(exc, OutlookClassicError):
        return str(exc)
    return (
        "Outlook Classic could not open the local mail profile. Open Outlook Classic, "
        "finish signing into the desired account, then rerun the wizard."
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Check DeskBob's local Outlook connection.")
    parser.add_argument("--status", action="store_true", help="Check the local Outlook profile.")
    return parser


async def _run_status() -> int:
    if not outlook_classic_installed():
        print("outlook-classic          unavailable (Outlook Classic is not installed)")
        return 2
    status = await WindowsOutlookClassicService().status()
    if not status["available"]:
        print(f"outlook-classic          unavailable ({status['message']})")
        return 2
    stores = ", ".join(status["stores"])
    print(f"outlook-classic          connected locally ({stores})")
    return 0


def run(argv: Sequence[str] | None = None) -> int:
    _parser().parse_args(argv)
    return asyncio.run(_run_status())


def main() -> None:
    raise SystemExit(run())


if __name__ == "__main__":
    main()
