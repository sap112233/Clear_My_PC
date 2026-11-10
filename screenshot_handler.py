"""Скриншоты: найти, дать осознанное имя, унести в 'мусор'."""
from datetime import datetime
from pathlib import Path

import config
import platform_tools as pt
from utils import sanitize, logged_move


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
    config.MUSOR.mkdir(parents=True, exist_ok=True)
    dst = config.MUSOR / build_name(src, app, title)
    return logged_move(src, dst, history)


def collect() -> list[Path]:
    out = []
    visited = set()
    for folder in (config.DESKTOP, config.MUSOR):
        resolved_folder = folder.resolve()
        if resolved_folder in visited:
            continue
        visited.add(resolved_folder)
        if folder.is_dir():
            out += [f for f in sorted(folder.iterdir()) if is_screenshot(f)]
    return out


def set_system_capture_location() -> None:
    pt.set_screenshot_location(config.MUSOR)