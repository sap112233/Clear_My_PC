"""Safe delayed archiving for installers matched to newly installed apps."""
from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import organization
import platform_tools as pt
import utils

INSTALLER_RETENTION_OPTIONS = (0, 15, 30, 60, 240, 1440)


def validate_installer_retention(value: object) -> int:
    if (
        not isinstance(value, int)
        or isinstance(value, bool)
        or value not in INSTALLER_RETENTION_OPTIONS
    ):
        raise ValueError("Недопустимый срок хранения установщиков.")
    return value


def validate_pending_installers(value: object) -> list[dict]:
    if not isinstance(value, list):
        raise ValueError("Очередь установщиков должна быть списком.")
    pending = []
    seen = set()
    for entry in value:
        if (
            not isinstance(entry, dict)
            or not isinstance(entry.get("path"), str)
            or not entry["path"]
            or not isinstance(entry.get("app"), str)
            or not entry["app"].strip()
            or not isinstance(entry.get("due"), str)
        ):
            raise ValueError("Запись в очереди установщиков повреждена.")
        try:
            due = datetime.fromisoformat(entry["due"])
        except ValueError as exc:
            raise ValueError("Срок в очереди установщиков повреждён.") from exc
        if due.tzinfo is not None:
            raise ValueError("Срок в очереди установщиков должен быть локальным.")
        key = str(Path(entry["path"]).resolve()).casefold()
        if key not in seen:
            seen.add(key)
            pending.append({
                "path": entry["path"],
                "app": entry["app"].strip(),
                "due": entry["due"],
            })
    return pending


def matches_installed_app(installer: Path, app_name: str) -> bool:
    installer_name = "".join(
        character for character in installer.stem.casefold() if character.isalnum()
    )
    installed_name = "".join(
        character for character in app_name.casefold() if character.isalnum()
    )
    return bool(
        len(installer_name) >= 6
        and len(installed_name) >= 6
        and (installer_name in installed_name or installed_name in installer_name)
    )


def schedule_installer(
    pending: list[dict],
    installer: Path,
    app_name: str,
    delay_minutes: int,
    downloads: Path,
    excluded_folders: list[Path],
    now: datetime | None = None,
) -> bool:
    delay = validate_installer_retention(delay_minutes)
    if delay == 0:
        return False
    if (
        installer.is_symlink()
        or not installer.is_file()
        or installer.parent.resolve() != downloads.resolve()
        or installer.suffix.lower() not in pt.INSTALLER_EXTS
        or organization.is_excluded_path(installer, excluded_folders)
        or not matches_installed_app(installer, app_name)
    ):
        return False
    key = str(installer.resolve()).casefold()
    if any(str(Path(item["path"]).resolve()).casefold() == key for item in pending):
        return False
    due = (now or datetime.now()) + timedelta(minutes=delay)
    pending.append({"path": str(installer), "app": app_name, "due": due.isoformat()})
    return True


def expire_due_installers(
    pending: list[dict],
    installed_app_names: list[str],
    downloads: Path,
    quarantine: Path,
    history: list[dict],
    excluded_folders: list[Path],
    now: datetime | None = None,
) -> tuple[list[dict], list[Path]]:
    current_time = now or datetime.now()
    retained = []
    archived = []
    installed = [name for name in installed_app_names if name.strip()]

    for entry in pending:
        source = Path(entry["path"])
        if (
            source.is_symlink()
            or not source.is_file()
            or source.parent.resolve() != downloads.resolve()
            or source.suffix.lower() not in pt.INSTALLER_EXTS
            or organization.is_excluded_path(source, excluded_folders)
            or not any(matches_installed_app(source, name) for name in installed)
        ):
            continue
        if datetime.fromisoformat(entry["due"]) > current_time:
            retained.append(entry)
            continue
        if quarantine.is_symlink():
            raise ValueError(f"Папка архива не должна быть символической ссылкой: {quarantine}")
        destination = utils.unique_dst(
            utils.safe_child_path(quarantine, source.name)
        )
        archived.append(
            utils.logged_move(
                source,
                destination,
                history,
                allow_unique=False,
                action="trash",
                metadata={
                    "reason": "installer_retention",
                    "app": entry["app"],
                },
            )
        )
    return retained, archived
