"""Сортировка файлов рабочего стола по типам в папки 'Файлы/<тип>'."""
from __future__ import annotations

from pathlib import Path

import config
import screenshot_handler as shots
from utils import logged_move, save_json

TYPE_MAP = {
    "Изображения": {".png", ".jpg", ".jpeg", ".gif", ".heic", ".webp", ".svg", ".tiff", ".bmp"},
    "Видео": {".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v"},
    "Аудио": {".mp3", ".wav", ".flac", ".aac", ".m4a", ".ogg", ".aiff"},
    "Документы": {".pdf", ".doc", ".docx", ".txt", ".md", ".rtf", ".pages",
                  ".key", ".numbers", ".xls", ".xlsx", ".ppt", ".pptx", ".csv"},
    "Архивы": {".zip", ".rar", ".7z", ".tar", ".gz", ".dmg", ".pkg"},
    "Код": {".py", ".java", ".js", ".ts", ".html", ".css", ".json", ".sh", ".swift", ".ipynb"},
}
SKIP_NAMES = {".DS_Store", ".localized", "desktop.ini"}


def type_for(p: Path) -> str:
    ext = p.suffix.lower()
    for type_name, exts in TYPE_MAP.items():
        if ext in exts:
            return type_name
    return "Другое"


def collect() -> list[tuple[Path, str]]:
    out = []
    if not config.DESKTOP.is_dir():
        return out
    for f in sorted(config.DESKTOP.iterdir()):
        if not f.is_file() or f.name in SKIP_NAMES:
            continue
        if shots.is_screenshot(f):
            continue
        out.append((f, type_for(f)))
    return out


def run(history: list) -> None:
    items = collect()
    if not items:
        print("На рабочем столе нет файлов для сортировки.")
        return

    print(f"\nФайлов к сортировке: {len(items)}:")
    for f, t in items:
        print(f"  {f.name}  →  Файлы/{t}/")

    if input("\nПрименить? [y/N] ").strip().lower() != "y":
        print("Отменено.")
        return

    for f, t in items:
        logged_move(f, config.FILES_ROOT / t / f.name, history)
    save_json(config.HISTORY_PATH, history)
    print("Готово.")