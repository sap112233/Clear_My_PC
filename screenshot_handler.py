"""Скриншоты: найти, дать осознанное имя, унести в 'мусор'."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import config
import organization
import platform_tools as pt
import utils
from utils import logged_move, sanitize

SCREENSHOT_RETENTION_OPTIONS = (0, 15, 30, 60, 240)


def validate_retention_minutes(value: object) -> int:
    if (
        not isinstance(value, int)
        or isinstance(value, bool)
        or value not in SCREENSHOT_RETENTION_OPTIONS
    ):
        raise ValueError("Недопустимый срок хранения скриншотов.")
    return value


def is_screenshot(p: Path) -> bool:
    return (
        p.is_file()
        and not p.is_symlink()
        and p.suffix.lower() in config.SCREENSHOT_EXTS
        and p.name.startswith(config.SCREENSHOT_PREFIXES)
    )


def build_name(src: Path, app: str, title: str) -> str:
    ts = datetime.fromtimestamp(src.stat().st_mtime).strftime("%Y-%m-%d %H-%M")
    parts = [p for p in (app, title, ts) if p]
    return sanitize(" @ ".join(parts)) + src.suffix.lower()


def process(src: Path, history: list, live: bool = False) -> Path:
    app, title = pt.frontmost_app() if live else ("", "")
    if organization.is_excluded_path(config.MUSOR, config.EXCLUDED_FOLDERS):
        raise ValueError(f"Папка скриншотов защищена: {config.MUSOR}")
    config.MUSOR.mkdir(parents=True, exist_ok=True)
    dst = config.MUSOR / build_name(src, app, title)
    return logged_move(src, dst, history)


def collect() -> list[Path]:
    out = []
    visited = set()
    for folder in (config.DESKTOP, config.MUSOR):
        if organization.is_excluded_path(folder, config.EXCLUDED_FOLDERS):
            continue
        resolved_folder = folder.resolve()
        if resolved_folder in visited:
            continue
        visited.add(resolved_folder)
        if folder.is_dir():
            out += [
                f for f in sorted(folder.iterdir())
                if not organization.is_excluded_path(f, config.EXCLUDED_FOLDERS)
                and is_screenshot(f)
            ]
    return out


def set_system_capture_location() -> None:
    if organization.is_excluded_path(config.MUSOR, config.EXCLUDED_FOLDERS):
        raise ValueError(f"Папка скриншотов защищена: {config.MUSOR}")
    pt.set_screenshot_location(config.MUSOR)


def expire_old_screenshots(
    history: list[dict],
    retention_minutes: int,
    now: datetime | None = None,
) -> list[Path]:
    validate_retention_minutes(retention_minutes)
    if retention_minutes == 0:
        return []

    current_time = now or datetime.now()
    cutoff = current_time.timestamp() - retention_minutes * 60
    candidates = set(collect())
    screenshot_prefixes = config.SCREENSHOT_PREFIXES
    managed_root = config.MUSOR.resolve()
    for entry in history:
        if (
            entry.get("undone")
            or entry.get("action") not in {"move", "trash"}
            or not isinstance(entry.get("src"), str)
            or not Path(entry["src"]).name.startswith(screenshot_prefixes)
            or not isinstance(entry.get("dst"), str)
        ):
            continue
        destination = Path(entry["dst"])
        if (
            destination.parent.resolve() == managed_root
            and destination.is_file()
            and not destination.is_symlink()
            and not organization.is_excluded_path(
                destination, config.EXCLUDED_FOLDERS
            )
        ):
            candidates.add(destination)

    archived = []
    if config.QUARANTINE_DIR.is_symlink():
        raise ValueError(
            f"Папка архива скриншотов не должна быть символической ссылкой: "
            f"{config.QUARANTINE_DIR}"
        )
    archive_root = utils.safe_child_path(config.QUARANTINE_DIR, "timed-screenshots")
    for source in sorted(candidates):
        if (
            source.is_symlink()
            or not source.is_file()
            or organization.is_excluded_path(source, config.EXCLUDED_FOLDERS)
        ):
            continue
        if source.stat().st_mtime > cutoff:
            continue
        destination = utils.unique_dst(archive_root / source.name)
        if organization.is_excluded_path(destination, config.EXCLUDED_FOLDERS):
            continue
        archived.append(
            logged_move(
                source,
                destination,
                history,
                allow_unique=False,
                action="trash",
                metadata={"reason": "screenshot_retention"},
            )
        )
    return archived