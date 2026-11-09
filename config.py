"""DesktopKeeper — пути и константы (кроссплатформенно)."""
from pathlib import Path

import platform_tools as pt

HOME = Path.home()
DESKTOP = pt.desktop_dir()
DOWNLOADS = pt.downloads_dir()
MUSOR = DESKTOP / "мусор"
APPS_ROOT = DESKTOP / "Apps"
FILES_ROOT = DESKTOP / "Файлы"
APP_DIRS = pt.app_dirs()

# Данные приложения живут в домашней папке, а не рядом с кодом/exe
DATA_DIR = HOME / ".desktop-keeper"
DATA_DIR.mkdir(parents=True, exist_ok=True)
STATE_PATH = DATA_DIR / "state.json"
HISTORY_PATH = DATA_DIR / "history.json"
CONFIG_PATH = DATA_DIR / "config.json"

SCREENSHOT_PREFIXES = ("Screenshot", "Screen Shot", "Снимок экрана")
SCREENSHOT_EXTS = {".png", ".jpg", ".jpeg"}