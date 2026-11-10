"""Сортировка файлов рабочего стола по типам в папки 'Файлы/<тип>'."""
from __future__ import annotations

from pathlib import Path

import config
import screenshot_handler as shots
from utils import logged_move, save_json, unique_dst

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
        if f.is_symlink() or not f.is_file() or f.name in SKIP_NAMES:
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

    planned = []
    reserved = set()
    for source, type_name in items:
        destination = unique_dst(
            config.FILES_ROOT / type_name / source.name, reserved
        )
        planned.append((source, type_name, destination))

    print(f"\nФайлов к сортировке: {len(planned)}:")
    for source, _, destination in planned:
        print(f"  {source}  →  {destination}")

    if input("\nПрименить? [y/N] ").strip().lower() != "y":
        print("Отменено.")
        return

    for source, _, destination in planned:
        logged_move(source, destination, history, allow_unique=False)
    save_json(config.HISTORY_PATH, history)
    print("Готово.")