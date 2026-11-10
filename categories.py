"""Менеджер категорий: создание новых папок внутри Apps."""
from __future__ import annotations

from pathlib import Path

import config
import organization
from utils import load_json, safe_child_path, save_json, sanitize


def add_category(name: str) -> Path:
    folder = safe_child_path(config.APPS_ROOT, sanitize(name))
    if organization.is_excluded_path(folder, config.EXCLUDED_FOLDERS):
        raise ValueError(f"Папка категории защищена и не может быть изменена: {folder}")
    folder.mkdir(parents=True, exist_ok=True)
    cfg = load_json(config.CONFIG_PATH, {"categories": {}})
    cfg.setdefault("categories", {}).setdefault(folder.name, [])
    save_json(config.CONFIG_PATH, cfg)
    print(f"Категория создана: Apps/{folder.name}")
    return folder


def list_categories() -> list[str]:
    cfg = load_json(config.CONFIG_PATH, {"categories": {}})
    return list(cfg.get("categories", {}).keys())