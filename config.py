"""DesktopKeeper — пути и константы (кроссплатформенно)."""
from pathlib import Path
import os

import platform_tools as pt

HOME = Path.home()
DESKTOP = pt.desktop_dir()
DOWNLOADS = pt.downloads_dir()


def _desktop_child(name: str) -> Path:
    child = DESKTOP / name
    desktop_root = DESKTOP.resolve()
    resolved = child.resolve()
    if resolved == desktop_root or desktop_root not in resolved.parents:
        raise ValueError(f"Путь должен оставаться внутри рабочего стола: {child}")
    return child


MUSOR = _desktop_child("мусор")
APPS_ROOT = _desktop_child("Apps")
FILES_ROOT = _desktop_child("Файлы")
APP_DIRS = pt.app_dirs()

# Данные приложения живут в домашней папке, а не рядом с кодом/exe
DATA_DIR = HOME / ".desktop-keeper"
if DATA_DIR.is_symlink():
    raise ValueError(f"Папка данных DesktopKeeper не должна быть символической ссылкой: {DATA_DIR}")
DATA_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
if os.name == "posix":
    DATA_DIR.chmod(0o700)


def _private_child(name: str) -> Path:
    child = DATA_DIR / name
    if child.is_symlink() or child.resolve().parent != DATA_DIR.resolve():
        raise ValueError(f"Недопустимый путь данных DesktopKeeper: {child}")
    return child


STATE_PATH = DATA_DIR / "state.json"
HISTORY_PATH = DATA_DIR / "history.json"
CONFIG_PATH = DATA_DIR / "config.json"
QUARANTINE_DIR = _private_child("quarantine")
ROLLBACK_DIR = _private_child("rollback")

SCREENSHOT_PREFIXES = ("Screenshot", "Screen Shot", "Снимок экрана")
SCREENSHOT_EXTS = {".png", ".jpg", ".jpeg"}