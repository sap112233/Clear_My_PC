"""DesktopKeeper GUI: онбординг, опросник, скан с предпросмотром.
Запуск: python3 gui.py
"""
from __future__ import annotations

import logging
import os
import queue
import subprocess
import threading
import uuid
from datetime import datetime
from pathlib import Path
from time import monotonic

import customtkinter as ctk
from tkinter import filedialog, messagebox
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

import app_handler as apps
import autostart
import background_monitor
import categories as cats
import config
import file_sorter as sorter
import notify
import organization
import platform_tools as pt
import screenshot_handler as shots
import updater
import utils

logger = logging.getLogger(__name__)

ctk.set_appearance_mode("light")
ctk.set_default_color_theme("blue")

ACCENT = ("#6036D9", "#805CF0")
ACCENT_HOVER = ("#5128C7", "#6F49DF")
TEXT = ("#171923", "#F2F1F7")
MUTED = ("#71809A", "#A5ADC0")
SURFACE = ("#FFFFFF", "#22232A")
BACKGROUND = ("#F2F3F7", "#18191F")
SIDEBAR = ("#F8F8FB", "#1D1E25")
BORDER = ("#E6E5EA", "#34353F")
SEPARATOR = ("#ECECF0", "#34353F")
NAV_HOVER = ("#ECEAF3", "#2B2C35")
NAV_ACTIVE = ("#E5DDF8", "#342A4E")
BADGE_BG = ("#E9E1FA", "#382D53")
ICON_BG = ("#F0F0F3", "#30313A")
APP_MENU_BG = ("#F0EDF8", "#342A4E")
APP_MENU_BUTTON = ("#E5DDF8", "#443363")
APP_MENU_HOVER = ("#DAD0F2", "#55417D")
FOOTER_HOVER = ("#E8E8ED", "#2B2C35")

DEFAULT_CATEGORIES = {
    "Браузеры": ["Chrome", "Firefox", "Safari", "Brave", "Arc", "Tor Browser"],
    "Соц. сети": ["Discord", "Telegram", "WhatsApp", "Slack", "Zoom", "AyuGram"],
    "Программирование": ["Xcode", "IntelliJ", "Visual Studio Code", "PyCharm", "Cursor", "Zed", "Rider", "GitHub Desktop", "Docker"],
    "Видео": ["Final Cut", "DaVinci", "VLC", "IINA", "CapCut", "Compressor"],
    "Музыка": ["Logic Pro", "GarageBand", "Spotify", "Audacity", "Mixxx", "VirtualDJ", "MainStage"],
    "Графика/дизайн": ["Photoshop", "Figma", "Sketch", "Canva", "krita", "Pixelmator"],
    "Игры": ["Steam", "Epic", "Battle.net", "Minecraft", "Counter-Strike", "Terraria", "Geometry Dash", "Roblox", "tModLoader"],
    "Заметки": ["Notes", "Notion", "Obsidian", "Bear", "Evernote"],
    "Текст": ["Word", "Pages", "TextEdit", "Excel", "PowerPoint", "Outlook", "Numbers", "Keynote", "OneNote"],
    "Утилиты": ["CleanMyMac", "Unarchiver", "Alfred", "Keka", "AppCleaner", "Ollama", "LM Studio", "OneDrive", "AnyDesk"],
    "Анимация": ["After Effects", "Blender", "Motion"],
    "Apple приложения": ["Mail", "Calendar", "Maps", "FaceTime", "Photos"],
    "Другое": [],
}


def now() -> str:
    return datetime.now().isoformat()


def load_cfg() -> dict:
    cfg = utils.load_json(config.CONFIG_PATH, {})
    if not isinstance(cfg, dict):
        raise ValueError("Файл настроек должен содержать JSON-объект.")
    cfg.setdefault("theme", "light")
    if cfg["theme"] not in {"light", "dark"}:
        raise ValueError("Тема должна быть «light» или «dark».")
    ctk.set_appearance_mode(cfg["theme"])
    cfg.setdefault("categories", dict(DEFAULT_CATEGORIES))
    default_features = {
        "screenshots": True,
        "sort_files": True,
        "apps": True,
        "installers": True,
    }
    cfg.setdefault("features", dict(default_features))
    cfg.setdefault("screenshot_retention_minutes", 0)
    cfg["screenshot_retention_minutes"] = shots.validate_retention_minutes(
        cfg["screenshot_retention_minutes"]
    )
    cfg.setdefault("installer_retention_minutes", 0)
    cfg["installer_retention_minutes"] = (
        background_monitor.validate_installer_retention(
            cfg["installer_retention_minutes"]
        )
    )
    cfg.setdefault("pending_installer_cleanup", [])
    cfg["pending_installer_cleanup"] = (
        background_monitor.validate_pending_installers(
            cfg["pending_installer_cleanup"]
        )
    )
    cfg.setdefault("background_monitoring", False)
    if not isinstance(cfg["background_monitoring"], bool):
        raise ValueError("Настройка фонового мониторинга должна быть логической.")
    cfg.setdefault("folders", {"musor": "мусор", "apps": "Apps", "files": "Файлы"})
    cfg.setdefault("layout_mode", "automatic")
    cfg.setdefault("locations", {})
    cfg.setdefault("managed_roots", {key: [] for key in organization.LOCATION_KEYS})
    cfg["excluded_folders"] = [
        str(path)
        for path in organization.validate_excluded_folders(
            cfg.setdefault("excluded_folders", [])
        )
    ]
    config.EXCLUDED_FOLDERS = [Path(path) for path in cfg["excluded_folders"]]
    cfg.setdefault("app_categories", {})
    cfg.setdefault("custom_file_types", {})
    cfg.setdefault(
        "enabled_types",
        list(sorter.TYPE_MAP) + list(cfg["custom_file_types"]) + ["Другое"],
    )
    cfg.setdefault("onboarding_done", False)
    if not isinstance(cfg["categories"], dict):
        raise ValueError("Настройка категорий должна быть JSON-объектом.")
    cfg["categories"].setdefault("Другое", [])
    if not isinstance(cfg["features"], dict):
        raise ValueError("Настройка функций должна быть JSON-объектом.")
    for key, value in default_features.items():
        cfg["features"].setdefault(key, value)
    if not isinstance(cfg["enabled_types"], list):
        raise ValueError("Список типов файлов должен быть массивом.")
    if not isinstance(cfg["folders"], dict):
        raise ValueError("Настройка папок должна быть JSON-объектом.")
    for key, value in {"musor": "мусор", "apps": "Apps", "files": "Файлы"}.items():
        cfg["folders"].setdefault(key, value)
    if any(
        not isinstance(category, str)
        or not isinstance(names, list)
        or any(not isinstance(name, str) for name in names)
        for category, names in cfg["categories"].items()
    ):
        raise ValueError("Категории должны содержать списки имён приложений.")
    if any(not isinstance(value, bool) for value in cfg["features"].values()):
        raise ValueError("Все настройки функций должны быть логическими значениями.")
    if any(not isinstance(value, str) for value in cfg["folders"].values()):
        raise ValueError("Имена рабочих папок должны быть строками.")
    if any(not isinstance(value, str) for value in cfg["enabled_types"]):
        raise ValueError("Названия типов файлов должны быть строками.")
    organization.migrate_enabled_file_types(cfg)
    if cfg["layout_mode"] not in {"automatic", "custom"}:
        raise ValueError("Неизвестный режим расположения папок.")
    if not isinstance(cfg["locations"], dict):
        raise ValueError("Настройка расположения папок должна быть JSON-объектом.")
    if not isinstance(cfg["managed_roots"], dict):
        raise ValueError("Список папок для отката должен быть JSON-объектом.")
    for key in organization.LOCATION_KEYS:
        roots = cfg["managed_roots"].get(key, [])
        if not isinstance(roots, list):
            raise ValueError("Список папок для отката должен содержать массивы путей.")
        cfg["managed_roots"][key] = list(dict.fromkeys(
            str(organization.validate_custom_root(root, config.HOME))
            for root in roots
        ))
    if not isinstance(cfg["app_categories"], dict) or any(
        not isinstance(app, str)
        or not isinstance(category, str)
        or category not in cfg["categories"]
        for app, category in cfg["app_categories"].items()
    ):
        raise ValueError("Назначения приложений должны ссылаться на существующие категории.")
    cfg["custom_file_types"] = organization.validate_custom_file_types(
        cfg["custom_file_types"], sorter.TYPE_MAP
    )
    allowed_types = set(sorter.TYPE_MAP) | set(cfg["custom_file_types"]) | {"Другое"}
    if any(value not in allowed_types for value in cfg["enabled_types"]):
        raise ValueError("Включён неизвестный тип файлов.")
    category_folders = set()
    for category in cfg["categories"]:
        folder = organization.category_folder_name(category)
        if folder.casefold() in category_folders:
            raise ValueError(f"Две категории используют одну папку: {folder}")
        category_folders.add(folder.casefold())
        utils.safe_child_path(config.DESKTOP, folder)
    return cfg


def apply_folder_names(cfg: dict) -> None:
    locations = organization.resolve_locations(cfg, config.DESKTOP, config.HOME)
    config.MUSOR = locations["screenshots"]
    config.FILES_ROOT = locations["files"]
    config.APPS_ROOT = locations["apps"]
    config.EXCLUDED_FOLDERS = organization.validate_excluded_folders(
        cfg.get("excluded_folders", [])
    )


def unique_destination(path: Path, reserved: set[Path]) -> Path:
    reserved_names = {str(item).casefold() for item in reserved}
    candidate = path
    index = 2
    while (
        candidate.exists()
        or candidate.is_symlink()
        or str(candidate).casefold() in reserved_names
    ):
        candidate = path.with_name(f"{path.stem} ({index}){path.suffix}")
        index += 1
    reserved.add(candidate)
    return candidate


def reserve_destination(path: Path, reserved: set[Path]) -> Path:
    return unique_destination(path, reserved)


class ToolTip:
    """Подсказка при наведении."""
    def __init__(self, widget, text: str):
        self.w, self.text, self.tip = widget, text, None
        widget.bind("<Enter>", self.show)
        widget.bind("<Leave>", self.hide)

    def show(self, _=None):
        if self.tip:
            return
        self.tip = ctk.CTkToplevel()
        self.tip.overrideredirect(True)
        self.tip.attributes("-topmost", True)
        self.tip.configure(fg_color="#1f1f1f")
        ctk.CTkLabel(self.tip, text=self.text, wraplength=340, justify="left",
                     fg_color="transparent", font=("", 12)).pack(padx=10, pady=8)
        self.tip.geometry(f"+{self.w.winfo_rootx() + 16}+{self.w.winfo_rooty() + self.w.winfo_height() + 6}")

    def hide(self, _=None):
        if self.tip:
            self.tip.destroy()
            self.tip = None


class SettingsWindow(ctk.CTkToplevel):
    def __init__(self, parent, cfg: dict, on_saved=None):
        super().__init__(parent)
        self.cfg = cfg
        self.on_saved = on_saved
        self.title("Папки и сортировка")
        self.geometry("760x900")
        self.transient(parent)
        self.grab_set()
        self.location_vars = {}
        self.type_vars = {}
        self.custom_types = {
            name: list(extensions)
            for name, extensions in cfg["custom_file_types"].items()
        }
        self.enabled_types = set(cfg["enabled_types"])

        ctk.CTkLabel(
            self, text="Скриншоты по таймеру", font=("", 18, "bold")
        ).pack(anchor="w", padx=16, pady=(14, 4))
        ctk.CTkLabel(
            self,
            text="Пока DesktopKeeper запущен, просроченные скриншоты перемещаются "
            "в обратимый архив. Таймер выключен по умолчанию.",
            anchor="w",
            wraplength=700,
            text_color=MUTED,
        ).pack(anchor="w", padx=16, pady=(0, 4))
        retention_labels = {
            0: "Выключен",
            15: "15 минут",
            30: "30 минут",
            60: "1 час",
            240: "4 часа",
        }
        self.retention_values = {
            label: minutes for minutes, label in retention_labels.items()
        }
        self.retention_var = ctk.StringVar(
            value=retention_labels[cfg["screenshot_retention_minutes"]]
        )
        ctk.CTkOptionMenu(
            self,
            values=list(self.retention_values),
            variable=self.retention_var,
            width=180,
        ).pack(anchor="w", padx=16, pady=(0, 8))

        ctk.CTkLabel(
            self, text="Установщики после установки приложения", font=("", 18, "bold")
        ).pack(anchor="w", padx=16, pady=(10, 4))
        ctk.CTkLabel(
            self,
            text="Таймер запускается только после обнаружения нового приложения "
            "и совпадающего установщика в Загрузках. Архив обратим; по умолчанию "
            "автоматическое перемещение выключено.",
            anchor="w",
            wraplength=700,
            text_color=MUTED,
        ).pack(anchor="w", padx=16, pady=(0, 4))
        installer_retention_labels = {
            0: "Выключен — только вручную",
            15: "15 минут",
            30: "30 минут",
            60: "1 час",
            240: "4 часа",
            1440: "24 часа",
        }
        self.installer_retention_values = {
            label: minutes for minutes, label in installer_retention_labels.items()
        }
        self.installer_retention_var = ctk.StringVar(
            value=installer_retention_labels[cfg["installer_retention_minutes"]]
        )
        ctk.CTkOptionMenu(
            self,
            values=list(self.installer_retention_values),
            variable=self.installer_retention_var,
            width=260,
        ).pack(anchor="w", padx=16, pady=(0, 8))

        ctk.CTkLabel(
            self, text="Куда раскладывать", font=("", 18, "bold")
        ).pack(anchor="w", padx=16, pady=(14, 6))
        ctk.CTkButton(
            self,
            text="Защищённые папки…",
            width=180,
            command=self.edit_excluded_folders,
        ).pack(anchor="w", padx=16, pady=(0, 8))
        self.mode_var = ctk.StringVar(value=cfg["layout_mode"])
        modes = ctk.CTkFrame(self, fg_color="transparent")
        modes.pack(fill="x", padx=14)
        ctk.CTkRadioButton(
            modes,
            text="Автоматические папки на рабочем столе",
            variable=self.mode_var,
            value="automatic",
            command=self.update_location_state,
        ).pack(anchor="w", pady=2)
        ctk.CTkLabel(
            self,
            text="Для безопасности собственные папки должны находиться внутри домашней папки.",
            anchor="w",
            text_color="#9a9a9a",
        ).pack(anchor="w", padx=16, pady=(0, 4))
        ctk.CTkRadioButton(
            modes,
            text="Выбрать свои папки",
            variable=self.mode_var,
            value="custom",
            command=self.update_location_state,
        ).pack(anchor="w", pady=2)

        defaults = organization.default_locations(config.DESKTOP, cfg["folders"])
        for key, label in (
            ("screenshots", "Скриншоты"),
            ("files", "Файлы"),
            ("apps", "Ярлыки приложений"),
        ):
            row = ctk.CTkFrame(self, fg_color="transparent")
            row.pack(fill="x", padx=14, pady=3)
            ctk.CTkLabel(row, text=label, width=145, anchor="w").pack(side="left")
            initial = cfg["locations"].get(key, str(defaults[key]))
            var = ctk.StringVar(value=initial)
            entry = ctk.CTkEntry(row, textvariable=var)
            entry.pack(side="left", fill="x", expand=True, padx=5)
            browse = ctk.CTkButton(
                row,
                text="Обзор…",
                width=80,
                command=lambda selected=var: self.browse_location(selected),
            )
            browse.pack(side="left")
            self.location_vars[key] = (var, entry, browse)

        ctk.CTkLabel(
            self, text="Сортировка файлов", font=("", 18, "bold")
        ).pack(anchor="w", padx=16, pady=(14, 4))
        types_frame = ctk.CTkScrollableFrame(self, height=180)
        types_frame.pack(fill="x", padx=14, pady=4)
        self.types_frame = types_frame
        self.render_file_types()

        custom = ctk.CTkFrame(self, fg_color="transparent")
        custom.pack(fill="x", padx=14, pady=(6, 2))
        self.new_type_entry = ctk.CTkEntry(
            custom, placeholder_text="Новая папка, например «Книги»", width=250
        )
        self.new_type_entry.pack(side="left", padx=(0, 6))
        self.new_extensions_entry = ctk.CTkEntry(
            custom, placeholder_text="Расширения: epub, mobi", width=270
        )
        self.new_extensions_entry.pack(side="left", padx=6)
        ctk.CTkButton(custom, text="Добавить тип", width=100,
                      command=self.add_custom_type).pack(side="left", padx=6)

        buttons = ctk.CTkFrame(self, fg_color="transparent")
        buttons.pack(fill="x", padx=14, pady=(12, 14), side="bottom")
        ctk.CTkButton(buttons, text="Сохранить", command=self.save).pack(side="left")
        ctk.CTkButton(
            buttons, text="Отмена", fg_color="#3a3a3a", command=self.destroy
        ).pack(side="right")
        self.update_location_state()

    def browse_location(self, variable):
        initial = Path(variable.get()).expanduser() if variable.get().strip() else config.HOME
        if not initial.is_dir():
            initial = initial.parent if initial.parent.is_dir() else config.HOME
        selected = filedialog.askdirectory(
            parent=self,
            initialdir=str(initial),
            title="Выбери папку назначения",
        )
        if selected:
            variable.set(selected)

    def update_location_state(self):
        state = "normal" if self.mode_var.get() == "custom" else "disabled"
        for _, entry, browse in self.location_vars.values():
            entry.configure(state=state)
            browse.configure(state=state)

    def edit_excluded_folders(self):
        win = ctk.CTkToplevel(self)
        win.title("Защищённые папки")
        win.geometry("620x420")
        win.transient(self)
        win.grab_set()
        ctk.CTkLabel(
            win,
            text="Содержимое этих папок DesktopKeeper не будет сортировать или перемещать.",
            anchor="w",
            wraplength=570,
        ).pack(fill="x", padx=14, pady=(14, 8))
        rows = ctk.CTkScrollableFrame(win)
        rows.pack(fill="both", expand=True, padx=14, pady=6)

        def persist(paths: list[str]) -> bool:
            try:
                folders = organization.validate_excluded_folders(paths)
                updated = dict(self.cfg)
                updated["excluded_folders"] = [str(folder) for folder in folders]
                utils.save_json(config.CONFIG_PATH, updated)
                self.cfg.update(updated)
                config.EXCLUDED_FOLDERS = folders
            except (OSError, TypeError, ValueError) as exc:
                messagebox.showerror(
                    "Не удалось сохранить защищённые папки", str(exc), parent=win
                )
                return False
            return True

        def render():
            for widget in rows.winfo_children():
                widget.destroy()
            if not self.cfg["excluded_folders"]:
                ctk.CTkLabel(
                    rows, text="Пока нет защищённых папок.", text_color=MUTED
                ).pack(anchor="w", padx=8, pady=8)
            for folder in self.cfg["excluded_folders"]:
                row = ctk.CTkFrame(rows, fg_color="transparent")
                row.pack(fill="x", padx=4, pady=3)
                ctk.CTkLabel(
                    row, text=folder, anchor="w", wraplength=440
                ).pack(side="left", fill="x", expand=True, padx=6)
                ctk.CTkButton(
                    row,
                    text="Убрать",
                    width=72,
                    fg_color="#7a3b3b",
                    command=lambda selected=folder: remove(selected),
                ).pack(side="right")

        def remove(folder: str):
            remaining = [
                item for item in self.cfg["excluded_folders"] if item != folder
            ]
            if persist(remaining):
                render()

        def add():
            selected = filedialog.askdirectory(
                parent=win,
                title="Выбери папку, которую нужно защитить",
                mustexist=True,
            )
            if not selected:
                return
            if persist([*self.cfg["excluded_folders"], selected]):
                render()

        ctk.CTkButton(
            win, text="Добавить папку…", command=add
        ).pack(anchor="w", padx=14, pady=(4, 14))
        render()

    def render_file_types(self):
        for widget in self.types_frame.winfo_children():
            widget.destroy()
        self.type_vars = {}
        definitions = {**{name: [] for name in sorter.TYPE_MAP}, **self.custom_types,
                       "Другое": []}
        for name, extensions in definitions.items():
            selected = ctk.BooleanVar(value=name in self.enabled_types)
            self.type_vars[name] = selected
            row = ctk.CTkFrame(self.types_frame, fg_color="transparent")
            row.pack(fill="x", padx=4, pady=1)
            detail = f" ({', '.join(extensions)})" if extensions else ""
            ctk.CTkCheckBox(row, text=f"{name}{detail}", variable=selected).pack(
                side="left"
            )
            if name in self.custom_types:
                ctk.CTkButton(
                    row,
                    text="Удалить",
                    width=65,
                    height=24,
                    fg_color="#7a3b3b",
                    command=lambda item=name: self.remove_custom_type(item),
                ).pack(side="right")

    def add_custom_type(self):
        name = self.new_type_entry.get().strip()
        values = [
            item.strip()
            for item in self.new_extensions_entry.get().split(",")
            if item.strip()
        ]
        candidate = {**self.custom_types, name: values}
        try:
            validated = organization.validate_custom_file_types(
                candidate, sorter.TYPE_MAP
            )
        except ValueError as exc:
            messagebox.showerror("Неверный тип файлов", str(exc), parent=self)
            return
        self.custom_types = validated
        self.enabled_types.add(name)
        self.new_type_entry.delete(0, "end")
        self.new_extensions_entry.delete(0, "end")
        self.render_file_types()

    def remove_custom_type(self, name):
        self.custom_types.pop(name, None)
        self.enabled_types.discard(name)
        self.render_file_types()

    def save(self):
        updated = dict(self.cfg)
        updated["layout_mode"] = self.mode_var.get()
        updated["locations"] = {
            key: var.get().strip()
            for key, (var, _, _) in self.location_vars.items()
        }
        updated["custom_file_types"] = organization.validate_custom_file_types(
            self.custom_types, sorter.TYPE_MAP
        )
        updated["enabled_types"] = [
            name for name, var in self.type_vars.items() if var.get()
        ]
        updated["screenshot_retention_minutes"] = self.retention_values[
            self.retention_var.get()
        ]
        updated["installer_retention_minutes"] = (
            self.installer_retention_values[self.installer_retention_var.get()]
        )
        try:
            locations = organization.resolve_locations(
                updated, config.DESKTOP, config.HOME
            )
            managed = updated.setdefault(
                "managed_roots", {key: [] for key in organization.LOCATION_KEYS}
            )
            if updated["layout_mode"] == "custom":
                for key in organization.LOCATION_KEYS:
                    old_roots = managed.setdefault(key, [])
                    normalized = str(locations[key])
                    if normalized not in old_roots:
                        old_roots.append(normalized)
            utils.save_json(config.CONFIG_PATH, updated)
            self.cfg.clear()
            self.cfg.update(updated)
            apply_folder_names(self.cfg)
        except (OSError, TypeError, ValueError) as exc:
            messagebox.showerror("Не удалось сохранить настройки", str(exc), parent=self)
            return
        if self.on_saved:
            self.on_saved()
        self.destroy()


def app_roots_for(cfg: dict) -> list[Path]:
    roots = [
        config.APPS_ROOT,
        organization.default_locations(config.DESKTOP, cfg["folders"])["apps"],
        *map(Path, cfg["managed_roots"]["apps"]),
    ]
    return list(dict.fromkeys(roots))


def build_actions(cfg: dict, history: list[dict] | None = None) -> list[dict]:
    """Один проход по системе: собираем список предлагаемых действий."""
    apply_folder_names(cfg)
    actions: list[dict] = []
    reserved: set[Path] = set()
    feat = cfg["features"]

    if feat["screenshots"]:
        for f in shots.collect():
            if organization.is_excluded_path(f, config.EXCLUDED_FOLDERS):
                continue
            dst = reserve_destination(
                utils.safe_child_path(config.MUSOR, shots.build_name(f, "", "")),
                reserved,
            )
            if organization.is_excluded_path(dst, config.EXCLUDED_FOLDERS):
                continue
            if f == dst:
                continue
            actions.append({
                "kind": "move", "src": f, "dst": dst,
                "_source_root": (
                    "screenshots"
                    if f.resolve().parent == config.MUSOR.resolve()
                    else "desktop"
                ),
                "_destination_root": "screenshots",
                "desc": f"Переместить скриншот: {f}  →  {dst}",
            })

    if feat["sort_files"]:
        enabled = set(cfg["enabled_types"])
        for f, t in sorter.collect(cfg["custom_file_types"]):
            if (
                t not in enabled
                or organization.is_excluded_path(f, config.EXCLUDED_FOLDERS)
            ):
                continue
            dst = reserve_destination(
                utils.safe_child_path(config.FILES_ROOT, t, f.name), reserved
            )
            if organization.is_excluded_path(dst, config.EXCLUDED_FOLDERS):
                continue
            actions.append({
                "kind": "move", "src": f, "dst": dst,
                "_source_root": "desktop",
                "_destination_root": "files",
                "desc": f"Переместить: {f}  →  {dst}",
            })

    if feat["apps"]:
        state = utils.load_json(config.STATE_PATH, {"processed": []})
        if (
            not isinstance(state, dict)
            or not isinstance(state.get("processed", []), list)
            or any(not isinstance(item, str) for item in state.get("processed", []))
        ):
            raise ValueError("Файл состояния приложения имеет неверный формат.")
        active_aliases = organization.active_aliases(history or [])
        app_roots = app_roots_for(cfg)
        for app in apps.scan_applications():
            if organization.is_excluded_path(app, config.EXCLUDED_FOLDERS):
                continue
            name = apps.get_app_name(app)
            bid = apps.get_bundle_id(app)
            previous = active_aliases.get(str(app.resolve()))
            if previous and not (
                previous["path"].exists() or previous["path"].is_symlink()
            ):
                previous = None
            app_key = bid or name
            cat = cfg["app_categories"].get(app_key) or cfg["app_categories"].get(name)
            previous_category = (previous or {}).get("category")
            if previous_category not in cfg["categories"]:
                previous_category = None
            previous_folder = (
                previous["path"].parent.name
                if previous and previous["path"].parent.name in cfg["categories"]
                else None
            )
            cat = (
                cat
                or previous_category
                or apps.find_category(name, bid, cfg["categories"])
                or previous_folder
                or "Другое"
            )
            actual_dst = organization.app_destination(
                config.APPS_ROOT, cat, apps.get_app_name(app), pt.IS_MAC, pt.IS_LINUX
            )
            if organization.is_excluded_path(actual_dst, config.EXCLUDED_FOLDERS):
                continue
            kind = "alias"
            app_source = app
            if previous:
                app_source = previous["path"]
                if not any(
                    (relative := _path_relative_to(app_source.resolve(), root.resolve()))
                    is not None
                    and utils.safe_child_path(root, *relative.parts).resolve()
                    == app_source.resolve()
                    for root in app_roots
                ):
                    raise ValueError(
                        f"Найден ярлык вне разрешённых папок приложения: {app_source}"
                    )
                if app_source == actual_dst:
                    continue
                kind = "alias_move"
                actual_dst = unique_destination(actual_dst, reserved)
            else:
                if actual_dst.exists() or actual_dst.is_symlink():
                    continue
                if str(actual_dst).casefold() in {
                    str(item).casefold() for item in reserved
                }:
                    actual_dst = unique_destination(actual_dst, reserved)
                else:
                    reserved.add(actual_dst)
            actions.append({
                "kind": kind,
                "src": app_source,
                "_app_src": app,
                "_bid": bid,
                "_app_key": app_key,
                "app": name,
                "dst": actual_dst,
                "_destination_root": "apps",
                "_category": cat,
                "category_options": list(cfg["categories"]),
                "desc": (
                    f"{'Переместить ярлык' if kind == 'alias_move' else 'Создать ярлык'}: "
                    f"{app_source if kind == 'alias_move' else app}  →  {actual_dst}"
                ),
            })

    if feat["installers"]:
        app_names = {apps.get_app_name(a).lower() for a in apps.scan_applications()}
        for ins in apps.scan_downloads():
            if organization.is_excluded_path(ins, config.EXCLUDED_FOLDERS):
                continue
            n = ins.stem.lower()
            if any(n in a or a in n for a in app_names):
                dst = reserve_destination(config.QUARANTINE_DIR / ins.name, reserved)
                actions.append({"kind": "trash", "src": ins, "dst": dst,
                                "_destination_root": "quarantine",
                                "desc": f"Переместить установщик: {ins}  →  {dst}"})
    return actions


def _path_relative_to(path: Path, root: Path) -> Path | None:
    try:
        return path.relative_to(root)
    except ValueError:
        return None


def validate_action_source(path: Path, roots: list[Path], *, direct_child: bool) -> None:
    if path.is_symlink():
        raise ValueError(f"Исходный путь заменён символической ссылкой: {path}")
    resolved = path.resolve()
    for root in roots:
        root_resolved = root.resolve()
        relative = _path_relative_to(resolved, root_resolved)
        if relative is None or not relative.parts:
            continue
        if direct_child and len(relative.parts) != 1:
            continue
        checked = utils.safe_child_path(root, *relative.parts)
        if checked.resolve() == resolved:
            return
    raise ValueError(f"Исходный путь находится вне разрешённых папок: {path}")


def apply_actions(actions: list[dict], history: list, cfg: dict) -> int:
    apply_folder_names(cfg)
    roots = {
        "screenshots": config.MUSOR,
        "files": config.FILES_ROOT,
        "apps": config.APPS_ROOT,
        "quarantine": config.QUARANTINE_DIR,
    }
    batch = uuid.uuid4().hex
    state = utils.load_json(config.STATE_PATH, {"processed": []})
    if not isinstance(state, dict) or not isinstance(state.get("processed", []), list):
        raise ValueError("Файл состояния приложения имеет неверный формат.")
    done = 0
    state.setdefault("processed", [])
    for a in actions:
        if not a["var"].get():
            continue
        try:
            src = a["src"]
            excluded_folders = organization.validate_excluded_folders(
                cfg.get("excluded_folders", [])
            )
            if organization.is_excluded_path(src, excluded_folders) or organization.is_excluded_path(
                a["dst"], excluded_folders
            ):
                raise ValueError(
                    "Действие затрагивает защищённую папку. Выполни новое сканирование."
                )
            if not (src.exists() or src.is_symlink()):
                raise FileNotFoundError(f"Исходный файл больше не существует: {src}")
            kind_roots = {
                "move": (
                    [config.MUSOR]
                    if a.get("_source_root") == "screenshots"
                    else [config.DESKTOP]
                ),
                "trash": [config.DOWNLOADS],
                "alias": config.APP_DIRS,
                "alias_move": app_roots_for(cfg),
            }
            validate_action_source(
                src,
                kind_roots[a["kind"]],
                direct_child=a["kind"] not in {"alias", "alias_move"},
            )
            destination_root = roots[a["_destination_root"]]
            try:
                relative_destination = a["dst"].relative_to(destination_root)
            except ValueError as exc:
                raise ValueError(
                    f"Путь назначения изменился после предпросмотра: {a['dst']}"
                ) from exc
            checked_destination = utils.safe_child_path(
                destination_root, *relative_destination.parts
            )
            if checked_destination != a["dst"]:
                raise ValueError(
                    f"Путь назначения изменился после предпросмотра: {a['dst']}"
                )
            if a["kind"] == "move":
                if a["dst"].exists() or a["dst"].is_symlink():
                    raise FileExistsError(f"Путь назначения уже занят: {a['dst']}. Выполни новое сканирование.")
                utils.logged_move(src, a["dst"], history, allow_unique=False)
                history[-1]["batch"] = batch
            elif a["kind"] == "trash":
                if a["dst"].exists() or a["dst"].is_symlink():
                    raise FileExistsError(f"Путь назначения уже занят: {a['dst']}. Выполни новое сканирование.")
                utils.logged_move(src, a["dst"], history, allow_unique=False)
                history[-1]["batch"] = batch
            elif a["kind"] == "alias":
                actual_dst = a["dst"]
                if actual_dst.exists() or actual_dst.is_symlink():
                    raise FileExistsError(f"Ярлык уже существует: {actual_dst}. Выполни новое сканирование.")
                real = pt.create_shortcut(a["src"], a["dst"])
                app_name = a.get("app", a["src"].stem)
                if app_name not in state["processed"]:
                    state["processed"].append(app_name)
                if a.get("_bid") and a["_bid"] not in state["processed"]:
                    state["processed"].append(a["_bid"])
                cfg["app_categories"][a.get("_app_key", app_name)] = a["_category"]
                history.append({
                    "ts": now(), "action": "alias", "src": str(src),
                    "dst": str(real), "app": a.get("app", a["src"].stem),
                    "bundle_id": a.get("_bid"), "category": a["_category"],
                    "batch": batch,
                })
                utils.save_json(config.HISTORY_PATH, history)
                utils.save_json(config.STATE_PATH, state)
                utils.save_json(config.CONFIG_PATH, cfg)
            elif a["kind"] == "alias_move":
                if a["dst"].exists() or a["dst"].is_symlink():
                    raise FileExistsError(
                        f"Путь назначения уже занят: {a['dst']}. Выполни новое сканирование."
                    )
                utils.logged_move(
                    src,
                    a["dst"],
                    history,
                    allow_unique=False,
                    action="alias_move",
                    metadata={
                        "app_src": str(a["_app_src"]),
                        "app": a["app"],
                        "bundle_id": a.get("_bid"),
                        "category": a["_category"],
                        "batch": batch,
                    },
                )
                cfg["app_categories"][a.get("_app_key", a["app"])] = a["_category"]
                utils.save_json(config.HISTORY_PATH, history)
                utils.save_json(config.CONFIG_PATH, cfg)
            else:
                raise ValueError(f"Неизвестный тип действия: {a['kind']}")
            done += 1
        except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as e:
            messagebox.showerror("Ошибка", f"{a['src']}\n{e}")
    utils.save_json(config.HISTORY_PATH, history)
    utils.save_json(config.STATE_PATH, state)
    return done


def can_rollback(entry: dict) -> bool:
    if entry.get("undone"):
        return False
    if entry.get("action") in {"move", "trash", "alias_move"}:
        return bool(entry.get("src") and entry.get("dst"))
    if entry.get("action") == "alias":
        return bool(entry.get("dst") or entry.get("alias"))
    return False


def describe_history_entry(entry: dict) -> str:
    action = entry.get("action")
    if action == "alias":
        return f"Ярлык: {entry.get('app') or Path(entry.get('src') or '').name} → {entry.get('dst') or entry.get('alias')}"
    return f"{entry.get('src', 'Файл')} → {entry.get('dst', 'неизвестное место')}"


class ShotWatcher(FileSystemEventHandler):
    def __init__(self, on_shot):
        self.on_shot = on_shot

    def on_created(self, event):
        p = Path(event.src_path)
        if shots.is_screenshot(p) and utils.wait_stable(p):
            self.on_shot(p)

    def on_moved(self, event):
        p = Path(event.dest_path)
        if shots.is_screenshot(p) and utils.wait_stable(p):
            self.on_shot(p)


def safe_watch_directories(roots: list[Path]) -> list[Path]:
    directories = []
    seen = set()
    pending = list(roots)
    while pending:
        folder = pending.pop()
        if (
            folder.is_symlink()
            or not folder.is_dir()
            or organization.is_excluded_path(folder, config.EXCLUDED_FOLDERS)
        ):
            continue
        resolved = folder.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        directories.append(folder)
        with os.scandir(folder) as entries:
            for entry in entries:
                child = Path(entry.path)
                if (
                    entry.is_dir(follow_symlinks=False)
                    and not entry.name.startswith(".")
                    and not (pt.IS_MAC and child.suffix.lower() == ".app")
                    and not organization.is_excluded_path(
                        child, config.EXCLUDED_FOLDERS
                    )
                ):
                    pending.append(child)
    return directories


class ActivityWatcher(FileSystemEventHandler):
    def __init__(self, app_roots, downloads, on_application, on_installer):
        self.app_roots = [root.resolve() for root in app_roots]
        self.downloads = downloads.resolve()
        self.on_application = on_application
        self.on_installer = on_installer

    def _handle_path(self, path: Path) -> None:
        if path.is_symlink():
            return
        path = path.resolve()
        if organization.is_excluded_path(path, config.EXCLUDED_FOLDERS):
            return
        try:
            relative_to_downloads = path.relative_to(self.downloads)
        except ValueError:
            relative_to_downloads = None
        if (
            relative_to_downloads is not None
            and len(relative_to_downloads.parts) == 1
            and path.is_file()
            and path.suffix.lower() in pt.INSTALLER_EXTS
        ):
            self.on_installer(path)
            return

        supported = (
            (pt.IS_MAC and path.suffix.lower() == ".app" and path.is_dir())
            or (pt.IS_WIN and path.suffix.lower() == ".lnk" and path.is_file())
            or (
                pt.IS_LINUX
                and path.suffix.lower() == ".desktop"
                and path.is_file()
            )
        )
        if not supported:
            return
        for root in self.app_roots:
            try:
                relative = path.relative_to(root)
            except ValueError:
                continue
            if pt.IS_MAC and any(
                Path(*relative.parts[:index]).suffix.lower() == ".app"
                for index in range(1, len(relative.parts))
            ):
                return
            self.on_application(path)
            return

    def on_created(self, event):
        self._handle_path(Path(event.src_path))

    def on_moved(self, event):
        self._handle_path(Path(event.dest_path))


HELP_TEXT = """КАК ПОЛЬЗОВАТЬСЯ DesktopKeeper

1. Нажми «Сканировать систему».
   Приложение один раз пройдётся по рабочему столу, загрузкам
   и списку приложений и соберёт список предлагаемых действий.

2. Просмотри список и сними галочки с того, что трогать не нужно.
   Ничего не меняется, пока ты не нажмёшь «Применить».

3. В окне предпросмотра сними галочки с лишнего и нажми «Разрешить выбранное».
   Скриншоты уедут в папку «мусор» с понятными именами,
   файлы разложатся по папкам типов, для приложений создадутся
   ярлыки в категориях, установщики попадут в защищённое хранилище.

4. Если что-то пошло не так — «Откатить действия»:
   можно вернуть отдельные файлы или откатить все доступные действия.
   Ярлыки перемещаются в архив отката, не удаляясь безвозвратно.

ФОНОВЫЙ МОНИТОРИНГ
Включи тумблер «Фоновый мониторинг» — программа уведомит о новых скриншотах,
приложениях и установщиках. Перемещения требуют твоего подтверждения.
При включённом автозапуске разрешённый мониторинг включится после входа в систему.
Для установщиков можно отдельно выбрать срок до обратимого перемещения в архив.
Мониторинг действует только пока программа запущена и охватывает стандартные
папки системы; он не видит каждый менеджер пакетов, путь установки или кэш.
Сопоставление установщика выполняется по имени и не доказывает причинную связь.
В Linux нельзя универсально менять папку снимков для всех окружений и приложений.

КАТЕГОРИИ
Кнопка «Приложения» позволяет назначить категорию каждому приложению,
а в предпросмотре можно изменить конкретное назначение. Перемещения
ярлыков существующих приложений также требуют подтверждения и обратимы.
Кнопка «Категории» добавляет или удаляет папки для приложений.

ПАПКИ И ТИПЫ
Кнопка «Папки и типы» позволяет выбрать расположение папок,
включить нужные типы файлов и добавить собственную категорию
по расширениям. Пользовательские папки должны быть внутри домашней
папки пользователя. На Windows и macOS перемещаются только файлы
и создаваемые ярлыки, сами установленные приложения не перемещаются.
В «Папки и типы → Защищённые папки» добавь места, которые приложение
не должно сканировать или изменять. Это правило также проверяется перед
перемещением и откатом.

БЕЗОПАСНОСТЬ
Все действия логируются. Папки-категории и папки типов
создаются автоматически при первом применении."""


class Wizard(ctk.CTk):
    """Онбординг: приветствие → гайд → опросник → старт."""

    def __init__(self, cfg: dict, on_finish):
        super().__init__()
        self.cfg, self.on_finish = cfg, on_finish
        self.title("DesktopKeeper — первичная настройка")
        self.geometry("640x560")
        self.vars: dict = {}
        self.page = 0
        self.frame = ctk.CTkFrame(self)
        self.frame.pack(fill="both", expand=True, padx=16, pady=16)
        self.show_page(0)

    def clear(self):
        for w in self.frame.winfo_children():
            w.destroy()

    def nav(self, last=False):
        bar = ctk.CTkFrame(self.frame, fg_color="transparent")
        bar.pack(fill="x", side="bottom", pady=(12, 0))
        if self.page > 0:
            ctk.CTkButton(bar, text="← Назад", width=110, fg_color="#3a3a3a",
                          command=lambda: self.show_page(self.page - 1)).pack(side="left")
        ctk.CTkButton(bar, text="Начать сканирование" if last else "Далее →", width=190,
                      command=self.next).pack(side="right")

    def next(self):
        if self.page == 2:
            if not self.collect_answers():
                return
        if self.page == 3:
            self.cfg["onboarding_done"] = True
            utils.save_json(config.CONFIG_PATH, self.cfg)
            self.destroy()
            self.on_finish(scan_now=True)
            return
        self.show_page(self.page + 1)

    def collect_answers(self):
        f = self.cfg["folders"]
        requested = {
            "musor": self.vars["musor"].get().strip() or "мусор",
            "apps": self.vars["apps"].get().strip() or "Apps",
            "files": self.vars["files"].get().strip() or "Файлы",
        }
        try:
            for name in requested.values():
                utils.safe_child_path(config.DESKTOP, name)
        except ValueError as exc:
            messagebox.showerror("Недопустимое имя папки", str(exc), parent=self)
            return False
        f.update(requested)
        self.cfg["layout_mode"] = self.cfg.get("layout_mode", "automatic")
        for k in self.cfg["features"]:
            self.cfg["features"][k] = self.vars[f"feat_{k}"].get()
        try:
            organization.configure_screenshot_folder(
                self.cfg,
                self.vars["screenshot_folder_choice"].get(),
                self.selected_screenshot_folder,
                config.DESKTOP,
                config.HOME,
            )
        except (OSError, TypeError, ValueError) as exc:
            messagebox.showerror("Папка скриншотов", str(exc), parent=self)
            return False
        available_types = list(sorter.TYPE_MAP) + list(self.cfg["custom_file_types"]) + ["Другое"]
        enabled_before = set(self.cfg["enabled_types"])
        self.cfg["enabled_types"] = []
        for type_name in available_types:
            variable = self.vars.get(f"type_{type_name}")
            if variable is not None and variable.get():
                self.cfg["enabled_types"].append(type_name)
            elif variable is None and type_name in enabled_before:
                self.cfg["enabled_types"].append(type_name)
        try:
            organization.resolve_locations(self.cfg, config.DESKTOP, config.HOME)
        except (TypeError, ValueError) as exc:
            messagebox.showerror("Недопустимое расположение папок", str(exc), parent=self)
            return False
        return True

    def show_page(self, n: int):
        self.page = n
        self.clear()
        if n == 0:
            ctk.CTkLabel(self.frame, text="Привет! Я DesktopKeeper",
                         font=("", 26, "bold")).pack(pady=(40, 8))
            ctk.CTkLabel(self.frame, justify="left", font=("", 14), text=(
                "Я навожу порядок на рабочем столе без рук:\n\n"
                "• скриншоты → в папку «мусор» с осознанными именами\n"
                "• файлы → по папкам типов (картинки, документы, код…)\n"
                "• приложения → ярлыки по категориям внутри «Apps»\n"
                "• установщики → в защищённое хранилище\n\n"
                "Ничего не удаляется навсегда и не меняется без твоего подтверждения.")).pack(padx=30)
            self.nav()
        elif n == 1:
            ctk.CTkLabel(self.frame, text="Как это работает", font=("", 24, "bold")).pack(pady=(30, 8))
            ctk.CTkLabel(self.frame, justify="left", font=("", 14), text=(
                "1. «Сканировать систему» — один проход по столу, загрузкам и приложениям.\n"
                "2. Тебе показывается список действий с галочками — сними лишние.\n"
                "3. В окне предпросмотра выбери действия и подтверди их выполнение.\n"
                "4. «Откатить действия» — выборочный или полный откат записанных изменений.\n\n"
                "Важно: при первом запуске система спросит доступ к рабочему столу —\n"
                "разреши, иначе я не увижу файлы.")).pack(padx=24)
            self.nav()
        elif n == 2:
            ctk.CTkLabel(self.frame, text="Пара вопросов", font=("", 24, "bold")).pack(pady=(16, 6))
            box = ctk.CTkScrollableFrame(self.frame)
            box.pack(fill="both", expand=True, padx=8)
            ctk.CTkLabel(
                box,
                text="Куда складывать скриншоты?",
                justify="left",
                font=("", 14, "bold"),
            ).pack(anchor="w", padx=8, pady=(8, 2))
            ctk.CTkLabel(
                box,
                text="Папки назначения не создаются при запуске или сканировании. "
                "Новая папка появится только после подтверждённого действия.",
                justify="left",
                wraplength=540,
                text_color=MUTED,
            ).pack(anchor="w", padx=8, pady=(0, 4))
            self.vars["screenshot_folder_choice"] = ctk.StringVar(
                value="desktop"
            )
            self.selected_screenshot_folder = None
            ctk.CTkRadioButton(
                box,
                text=f"Предложить папку «{self.cfg['folders']['musor']}» "
                "на рабочем столе",
                variable=self.vars["screenshot_folder_choice"],
                value="desktop",
            ).pack(anchor="w", padx=16, pady=2)
            ctk.CTkLabel(
                box,
                text="Она будет создана только если ты применишь перемещение.",
                text_color=MUTED,
            ).pack(anchor="w", padx=42, pady=(0, 2))
            ctk.CTkRadioButton(
                box,
                text="Выбрать существующую папку",
                variable=self.vars["screenshot_folder_choice"],
                value="existing",
            ).pack(anchor="w", padx=16, pady=2)
            self.screenshot_folder_label = ctk.CTkLabel(
                box, text="Папка не выбрана", text_color=MUTED, anchor="w"
            )
            self.screenshot_folder_label.pack(anchor="w", padx=42, pady=(0, 2))

            def choose_screenshot_folder():
                selected = filedialog.askdirectory(
                    parent=self,
                    title="Выбери существующую папку для скриншотов",
                    mustexist=True,
                )
                if selected:
                    self.selected_screenshot_folder = selected
                    self.vars["screenshot_folder_choice"].set("existing")
                    self.screenshot_folder_label.configure(text=selected)

            ctk.CTkButton(
                box,
                text="Обзор…",
                width=100,
                command=choose_screenshot_folder,
            ).pack(anchor="w", padx=42, pady=(0, 2))
            ctk.CTkRadioButton(
                box,
                text="Оставлять скриншоты на месте",
                variable=self.vars["screenshot_folder_choice"],
                value="leave",
            ).pack(anchor="w", padx=16, pady=2)
            ctk.CTkLabel(box, text="Имена папок на рабочем столе:", justify="left",
                         font=("", 14, "bold")).pack(anchor="w", padx=8, pady=(8, 2))
            for key, label in (("musor", "куда складывать скриншоты"),
                               ("apps", "корень категорий приложений"),
                               ("files", "контейнер для файлов по типам")):
                row = ctk.CTkFrame(box, fg_color="transparent")
                row.pack(fill="x", padx=8, pady=2)
                ctk.CTkLabel(row, text=label, width=260, anchor="w").pack(side="left")
                e = ctk.CTkEntry(row, width=180)
                e.insert(0, self.cfg["folders"][key])
                e.pack(side="left")
                self.vars[key] = e
            ctk.CTkLabel(box, text="Что делать:", justify="left",
                         font=("", 14, "bold")).pack(anchor="w", padx=8, pady=(10, 2))
            for k, label in (("screenshots", "убирать скриншоты"),
                             ("sort_files", "сортировать файлы по типам"),
                             ("apps", "ярлыки приложений по категориям"),
                             ("installers", "установщики в защищённое хранилище")):
                v = ctk.BooleanVar(value=self.cfg["features"][k])
                ctk.CTkCheckBox(box, text=label, variable=v).pack(anchor="w", padx=16, pady=2)
                self.vars[f"feat_{k}"] = v
            ctk.CTkLabel(box, text="Какие папки типов создавать:", justify="left",
                         font=("", 14, "bold")).pack(anchor="w", padx=8, pady=(10, 2))
            for t in list(sorter.TYPE_MAP.keys()) + list(self.cfg["custom_file_types"]) + ["Другое"]:
                v = ctk.BooleanVar(value=t in self.cfg["enabled_types"])
                ctk.CTkCheckBox(box, text=t, variable=v).pack(anchor="w", padx=16, pady=2)
                self.vars[f"type_{t}"] = v
            ctk.CTkButton(
                box,
                text="Настроить расположение и типы файлов…",
                fg_color="#3a3a3a",
                command=lambda: SettingsWindow(
                    self,
                    self.cfg,
                    on_saved=self.sync_type_settings,
                ),
            ).pack(anchor="w", padx=16, pady=(8, 2))
            self.nav()
        else:
            ctk.CTkLabel(self.frame, text="Всё готово", font=("", 26, "bold")).pack(pady=(40, 8))
            ctk.CTkLabel(self.frame, justify="left", font=("", 14), text=(
                f"Папки: {self.cfg['folders']['musor']}, {self.cfg['folders']['apps']}, "
                f"{self.cfg['folders']['files']} появятся только для подтверждённых действий.\n\n"
                "Нажми «Начать сканирование» — я один раз пройду по системе\n"
                "и покажу, что и куда предлагаю переместить.")).pack(padx=30)
            self.nav(last=True)

    def sync_type_settings(self):
        for type_name, variable in self.vars.items():
            if type_name.startswith("type_"):
                variable.set(type_name[5:] in self.cfg["enabled_types"])


class Main(ctk.CTk):
    def __init__(self, cfg: dict, history: list[dict]):
        super().__init__()
        self.cfg = cfg
        self.actions: list[dict] = []
        self.history = history
        self.observer = None
        self.monitor_seen = set()
        self.monitor_seen_installers = set()
        self.monitor_events = queue.SimpleQueue()
        self.pending_monitor_events = []
        self.pending_shots: list[Path] = []
        self.shot_preview_window = None
        self.title("DesktopKeeper")
        self.geometry("1180x760")
        self.minsize(860, 600)
        self.configure(fg_color=BACKGROUND)

        sidebar = ctk.CTkFrame(self, width=250, corner_radius=0, fg_color=SIDEBAR)
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)

        brand = ctk.CTkFrame(sidebar, fg_color="transparent")
        brand.pack(fill="x", padx=18, pady=(22, 26))
        ctk.CTkLabel(
            brand, text="D", width=44, height=44, corner_radius=14,
            fg_color=ACCENT, text_color="#FFFFFF", font=("", 22, "bold"),
        ).pack(side="left")
        ctk.CTkLabel(
            brand, text="DesktopKeeper", text_color=TEXT, font=("", 16, "bold"),
        ).pack(side="left", padx=12)

        self.nav_buttons = {}
        self._add_nav(sidebar, "scan", "⌕  Сканирование", self.scan)
        self._add_nav(sidebar, "categories", "▦  Категории", self.edit_categories)
        self._add_nav(sidebar, "history", "↶  История", self.undo)
        self._add_nav(
            sidebar, "settings", "⚙  Настройки",
            lambda: SettingsWindow(self, self.cfg, self.settings_saved),
        )
        self._add_nav(sidebar, "apps", "▣  Приложения", self.edit_app_assignments)
        self._add_nav(sidebar, "help", "?  Справка", self.show_help)
        self._set_active_nav("scan")

        ctk.CTkFrame(sidebar, height=1, fg_color=BORDER).pack(
            side="bottom", fill="x", padx=18, pady=(0, 14)
        )
        self.theme = ctk.CTkSwitch(
            sidebar, text="Тёмная тема", command=self.toggle_theme,
            progress_color=ACCENT, button_color=ACCENT,
            button_hover_color=ACCENT_HOVER,
        )
        self.theme.pack(side="bottom", anchor="w", padx=22, pady=(0, 16))
        if self.cfg["theme"] == "dark":
            self.theme.select()
        self.auto = ctk.CTkSwitch(
            sidebar, text="Автозапуск", command=self.toggle_autostart,
            progress_color=ACCENT, button_color=ACCENT,
            button_hover_color=ACCENT_HOVER,
        )
        self.auto.pack(side="bottom", anchor="w", padx=22, pady=(0, 20))
        if autostart.is_enabled():
            self.auto.select()
        ToolTip(self.auto, "Запускать DesktopKeeper при входе в систему")
        self.mon = ctk.CTkSwitch(
            sidebar, text="Фоновый мониторинг", command=self.toggle_watch,
            progress_color=ACCENT, button_color=ACCENT,
            button_hover_color=ACCENT_HOVER,
        )
        self.mon.pack(side="bottom", anchor="w", padx=22, pady=(0, 12))
        ToolTip(
            self.mon,
            "По твоему разрешению следит за новыми скриншотами, приложениями "
            "и установщиками; файлы не перемещаются без подтверждения.",
        )
        self.monitor_status = ctk.CTkLabel(
            sidebar, text="●  Мониторинг выключен", text_color=MUTED,
            font=("", 12),
        )
        self.monitor_status.pack(side="bottom", anchor="w", padx=22, pady=(0, 8))

        content = ctk.CTkFrame(self, fg_color="transparent")
        content.pack(side="left", fill="both", expand=True, padx=38, pady=(28, 22))

        header = ctk.CTkFrame(content, fg_color="transparent")
        header.pack(fill="x", pady=(0, 26))
        heading = ctk.CTkFrame(header, fg_color="transparent")
        heading.pack(side="left", fill="x", expand=True)
        ctk.CTkLabel(
            heading, text="Сканирование", text_color=TEXT,
            font=("", 25, "bold"),
        ).pack(anchor="w")
        self.scan_summary = ctk.CTkLabel(
            heading, text="Запусти проверку, чтобы увидеть файлы для уборки",
            text_color=MUTED, font=("", 14),
        )
        self.scan_summary.pack(anchor="w", pady=(5, 0))
        self.btn_scan = ctk.CTkButton(
            header, text="Сканировать", width=188, height=46,
            corner_radius=13, fg_color=ACCENT, hover_color=ACCENT_HOVER,
            font=("", 14, "bold"), command=self.scan,
        )
        self.btn_scan.pack(side="right", padx=(18, 0))
        ToolTip(self.btn_scan, "Проверить рабочий стол, загрузки и приложения")

        stats = ctk.CTkFrame(content, fg_color="transparent")
        stats.pack(fill="x", pady=(0, 22))
        self.stat_values = {}
        for key, title, caption in (
            ("screenshots", "Скриншоты", "Скриншоты"),
            ("installers", "Установщики", "Установщики"),
            ("files", "Файлы для сортировки", "Файлы"),
        ):
            card = ctk.CTkFrame(
                stats, fg_color=SURFACE, corner_radius=18,
                border_width=1, border_color=BORDER,
            )
            card.pack(side="left", fill="x", expand=True, padx=(0, 14))
            ctk.CTkLabel(
                card, text="0", text_color=TEXT, font=("", 22, "bold"),
            ).pack(anchor="w", padx=18, pady=(13, 0))
            value = card.winfo_children()[-1]
            detail = ctk.CTkLabel(
                card, text=f"{caption} · 0 Б", text_color=MUTED,
                font=("", 12),
            )
            detail.pack(anchor="w", padx=18, pady=(0, 13))
            self.stat_values[key] = (value, detail)

        self.list = ctk.CTkScrollableFrame(
            content, fg_color="transparent", corner_radius=0,
        )
        self.list.pack(fill="both", expand=True)
        self.status = ctk.CTkLabel(
            content, text="Ничего не изменится без твоего подтверждения",
            anchor="w", text_color=MUTED, font=("", 12),
        )
        self.status.pack(fill="x", pady=(10, 10))

        footer = ctk.CTkFrame(content, fg_color="transparent")
        footer.pack(fill="x")
        self.btn_apply = ctk.CTkButton(
            footer, text="Применить (0)", width=216, height=44,
            corner_radius=12, fg_color=ACCENT, hover_color=ACCENT_HOVER,
            font=("", 14, "bold"), state="disabled", command=self.apply,
        )
        self.btn_apply.pack(side="left")
        self.btn_undo = ctk.CTkButton(
            footer, text="Откатить последнее", height=44,
            fg_color="transparent", hover_color=FOOTER_HOVER,
            text_color=MUTED, font=("", 13, "bold"), command=self.undo,
        )
        self.btn_undo.pack(side="left", padx=(18, 0))
        self.last_scan = None
        self._show_empty_state()
        self.protocol("WM_DELETE_WINDOW", self.close)
        if self.cfg["background_monitoring"]:
            self.mon.select()
            self.after(500, self.toggle_watch)
        self.after(1500, self.schedule_update_check)
        self.after(5000, self.run_screenshot_retention_check)
        self.after(5000, self.run_installer_retention_check)
        self.after(250, self._drain_monitor_events)

    def _add_nav(self, parent, key, text, command):
        def navigate():
            self._set_active_nav(key)
            command()

        button = ctk.CTkButton(
            parent, text=text, height=38, anchor="w", corner_radius=11,
            fg_color="transparent", hover_color=NAV_HOVER, text_color=MUTED,
            font=("", 13, "bold"), command=navigate,
        )
        button.pack(fill="x", padx=18, pady=3)
        self.nav_buttons[key] = button

    def _set_active_nav(self, selected):
        for key, button in self.nav_buttons.items():
            active = key == selected
            button.configure(
                fg_color=NAV_ACTIVE if active else "transparent",
                text_color=ACCENT if active else MUTED,
            )

    def _show_empty_state(self):
        for widget in self.list.winfo_children():
            widget.destroy()
        ctk.CTkLabel(
            self.list, text="Пока всё чисто", text_color=TEXT,
            font=("", 19, "bold"),
        ).pack(pady=(78, 6))
        ctk.CTkLabel(
            self.list,
            text="Нажми «Сканировать» — покажу, что можно безопасно разложить.",
            text_color=MUTED, font=("", 13),
        ).pack(pady=(0, 24))

    @staticmethod
    def _action_group(action):
        if action["kind"] == "trash":
            return "installers"
        if action.get("_destination_root") == "screenshots":
            return "screenshots"
        if action.get("_destination_root") == "files":
            return "files"
        return "apps"

    @staticmethod
    def _format_size(size):
        units = ("Б", "КБ", "МБ", "ГБ", "ТБ")
        value = float(size)
        for unit in units:
            if value < 1024 or unit == units[-1]:
                return f"{value:.0f} {unit}" if unit == "Б" else f"{value:.1f} {unit}"
            value /= 1024

    def _render_actions(self):
        for widget in self.list.winfo_children():
            widget.destroy()
        if not self.actions:
            self._show_empty_state()
            return

        groups = (
            ("screenshots", "Скриншоты", "▧"),
            ("installers", "Установщики", "▣"),
            ("files", "Файлы для сортировки", "▤"),
            ("apps", "Приложения", "◈"),
        )
        for key, title, icon in groups:
            actions = [item for item in self.actions if self._action_group(item) == key]
            if not actions:
                continue
            card = ctk.CTkFrame(
                self.list, fg_color=SURFACE, corner_radius=18,
                border_width=1, border_color=BORDER,
            )
            card.pack(fill="x", pady=(0, 12))
            heading = ctk.CTkFrame(card, fg_color="transparent")
            heading.pack(fill="x", padx=18, pady=(9, 6))
            ctk.CTkLabel(
                heading, text=title, text_color=TEXT, font=("", 13, "bold"),
            ).pack(side="left")
            badge = ctk.CTkLabel(
                heading, text="", corner_radius=10, fg_color=BADGE_BG,
                text_color=ACCENT, font=("", 10, "bold"), padx=10, pady=2,
            )
            badge.pack(side="right")
            for index, action in enumerate(actions):
                row = ctk.CTkFrame(
                    card, fg_color="transparent", corner_radius=0,
                )
                row.pack(fill="x", padx=12)
                if index:
                    ctk.CTkFrame(row, height=1, fg_color=SEPARATOR).pack(
                        fill="x", side="top",
                    )
                line = ctk.CTkFrame(row, fg_color="transparent")
                line.pack(fill="x", padx=4, pady=7)
                ctk.CTkCheckBox(
                    line, text="", variable=action["var"], width=22,
                    checkbox_width=19, checkbox_height=19,
                    fg_color=ACCENT, hover_color=ACCENT_HOVER,
                    command=self.refresh_count,
                ).pack(side="left", padx=(0, 10))
                ctk.CTkLabel(
                    line, text=icon, width=28, height=28, corner_radius=7,
                    fg_color=ICON_BG, text_color=MUTED,
                    font=("", 14, "bold"),
                ).pack(side="left", padx=(0, 12))
                ctk.CTkLabel(
                    line, text=action["src"].name, text_color=TEXT,
                    anchor="w", font=("", 12),
                ).pack(side="left", fill="x", expand=True)
                if action["kind"] in {"alias", "alias_move"}:
                    ctk.CTkOptionMenu(
                        line, values=action["category_options"],
                        variable=ctk.StringVar(value=action["_category"]),
                        width=135, height=28, fg_color=APP_MENU_BG,
                        button_color=APP_MENU_BUTTON, button_hover_color=APP_MENU_HOVER,
                        text_color=ACCENT,
                        command=lambda value, selected=action: self.update_app_category(
                            selected, value
                        ),
                    ).pack(side="right", padx=(8, 10))
                destination = ctk.CTkLabel(
                    line, text=f"→ {action['dst'].parent.name}",
                    text_color=MUTED, anchor="e", width=120, font=("", 11),
                )
                destination.pack(side="right", padx=(8, 4))
                action["_labels"] = [destination]
                try:
                    info = action["src"].stat()
                    action["_size"] = info.st_size if action["src"].is_file() else None
                except OSError:
                    action["_size"] = None
            action["_badge"] = badge
        self.refresh_count()

    def _refresh_stats(self):
        groups = ("screenshots", "installers", "files")
        captions = {
            "screenshots": "Скриншотов",
            "installers": "Установщиков",
            "files": "Файлов",
        }
        for key in groups:
            selected = [
                action for action in self.actions
                if self._action_group(action) == key and action["var"].get()
            ]
            total = sum(
                action.get("_size") or 0
                for action in selected
                if action.get("_size") is not None
            )
            value, detail = self.stat_values[key]
            value.configure(text=str(len(selected)))
            detail.configure(text=f"{captions[key]} · {self._format_size(total)}")
        for action in self.actions:
            badge = action.get("_badge")
            if badge:
                selected = sum(item["var"].get() for item in self.actions
                               if self._action_group(item) == self._action_group(action))
                total = sum(self._action_group(item) == self._action_group(action)
                            for item in self.actions)
                badge.configure(text=f"{selected} / {total}")

    def settings_saved(self):
        self.status.configure(text="Настройки сохранены. Новые назначения будут показаны при следующем сканировании.")

    def _drain_monitor_events(self):
        for _ in range(100):
            try:
                event_type, path, ready_at = self.monitor_events.get_nowait()
            except queue.Empty:
                break
            self.pending_monitor_events.append((event_type, path, ready_at))
        now_monotonic = monotonic()
        ready = [
            event for event in self.pending_monitor_events
            if event[2] <= now_monotonic
        ]
        self.pending_monitor_events = [
            event for event in self.pending_monitor_events
            if event[2] > now_monotonic
            or event[0] == "update_result"
        ]
        for event_type, payload, _ in ready:
            if event_type == "update_result":
                self._handle_update_result(payload)
            elif self.cfg["background_monitoring"] and event_type == "screenshot":
                self.queue_screenshot_review(payload)
            elif self.cfg["background_monitoring"] and event_type == "application":
                self._handle_new_application(payload)
            elif self.cfg["background_monitoring"] and event_type == "installer":
                self._handle_new_installer(payload)
        if self.winfo_exists():
            self.after(250, self._drain_monitor_events)

    def run_screenshot_retention_check(self):
        retention = self.cfg.get("screenshot_retention_minutes", 0)
        try:
            expired = shots.expire_old_screenshots(self.history, retention)
        except (OSError, TypeError, ValueError) as exc:
            messagebox.showerror("Таймер скриншотов", str(exc), parent=self)
        else:
            if expired:
                self.status.configure(
                    text=f"В архив перемещено скриншотов: {len(expired)}."
                )
                notify.notify(
                    f"В архив перемещено скриншотов по таймеру: {len(expired)}"
                )
        self.after(60_000, self.run_screenshot_retention_check)

    def _schedule_matched_installers(self, app_name: str) -> int:
        pending = list(self.cfg["pending_installer_cleanup"])
        scheduled = 0
        for installer in apps.scan_downloads():
            if background_monitor.schedule_installer(
                pending,
                installer,
                app_name,
                self.cfg["installer_retention_minutes"],
                config.DOWNLOADS,
                config.EXCLUDED_FOLDERS,
            ):
                scheduled += 1
        if scheduled:
            previous = self.cfg["pending_installer_cleanup"]
            self.cfg["pending_installer_cleanup"] = pending
            try:
                utils.save_json(config.CONFIG_PATH, self.cfg)
            except (OSError, TypeError, ValueError):
                self.cfg["pending_installer_cleanup"] = previous
                raise
        return scheduled

    def _handle_new_application(self, path: Path) -> None:
        if not path.exists() or path.is_symlink() or organization.is_excluded_path(
            path, config.EXCLUDED_FOLDERS
        ):
            return
        identity = str(path.resolve()).casefold()
        if identity in self.monitor_seen:
            return
        installed = apps.scan_applications()
        if not any(item.resolve() == path.resolve() for item in installed):
            return
        self.monitor_seen.add(identity)
        name = apps.get_app_name(path)
        try:
            scheduled = self._schedule_matched_installers(name)
        except (OSError, TypeError, ValueError) as exc:
            messagebox.showerror("Таймер установщиков", str(exc), parent=self)
            scheduled = 0
        if scheduled:
            notify.notify(
                f"Установщик {name} переместится в архив через "
                f"{self.cfg['installer_retention_minutes']} мин."
            )
        notify.notify(f"Обнаружено новое приложение: {name}")
        if messagebox.askyesno(
            "Новое приложение",
            f"Обнаружено приложение «{name}».\n"
            "Просканировать приложения и показать предлагаемый ярлык?",
            parent=self,
        ):
            self.scan()

    def _handle_new_installer(self, path: Path) -> None:
        if (
            not path.is_file()
            or path.is_symlink()
            or organization.is_excluded_path(path, config.EXCLUDED_FOLDERS)
        ):
            return
        identity = str(path.resolve()).casefold()
        if identity in self.monitor_seen_installers:
            return
        self.monitor_seen_installers.add(identity)
        installed_names = [apps.get_app_name(item) for item in apps.scan_applications()]
        matching = next(
            (
                name
                for name in installed_names
                if background_monitor.matches_installed_app(path, name)
            ),
            None,
        )
        try:
            scheduled = (
                self._schedule_matched_installers(matching) if matching else 0
            )
        except (OSError, TypeError, ValueError) as exc:
            messagebox.showerror("Таймер установщиков", str(exc), parent=self)
            scheduled = 0
        if scheduled:
            notify.notify(
                f"Установщик для {matching} переместится в обратимый архив через "
                f"{self.cfg['installer_retention_minutes']} мин."
            )
        else:
            notify.notify(
                f"Найден установщик: {path.name}. Он останется на месте до "
                "подтверждения после установки приложения."
            )

    def run_installer_retention_check(self):
        if self.cfg["pending_installer_cleanup"]:
            try:
                installed_names = [
                    apps.get_app_name(item) for item in apps.scan_applications()
                ]
                pending, archived = background_monitor.expire_due_installers(
                    self.cfg["pending_installer_cleanup"],
                    installed_names,
                    config.DOWNLOADS,
                    config.QUARANTINE_DIR,
                    self.history,
                    config.EXCLUDED_FOLDERS,
                )
                self.cfg["pending_installer_cleanup"] = pending
                utils.save_json(config.CONFIG_PATH, self.cfg)
            except (OSError, TypeError, ValueError) as exc:
                messagebox.showerror("Таймер установщиков", str(exc), parent=self)
            else:
                if archived:
                    self.status.configure(
                        text=f"Установщиков перемещено в обратимый архив: {len(archived)}."
                    )
                    notify.notify(
                        f"Установщики перемещены в обратимый архив: {len(archived)}"
                    )
        self.after(60_000, self.run_installer_retention_check)

    def toggle_theme(self):
        theme = "dark" if self.theme.get() else "light"
        previous = self.cfg["theme"]
        self.cfg["theme"] = theme
        try:
            utils.save_json(config.CONFIG_PATH, self.cfg)
        except (OSError, TypeError, ValueError) as exc:
            self.cfg["theme"] = previous
            self.theme.select() if previous == "dark" else self.theme.deselect()
            messagebox.showerror("Не удалось сохранить тему", str(exc), parent=self)
            return
        ctk.set_appearance_mode(theme)
        self.status.configure(
            text=f"Включена {'тёмная' if theme == 'dark' else 'светлая'} тема."
        )

    def schedule_update_check(self):
        today = datetime.now().date().isoformat()
        if self.cfg.get("last_update_check") == today:
            return
        threading.Thread(target=self._update_check, daemon=True).start()

    def _update_check(self):
        rel = updater.check_update()
        checked_at = datetime.now().date().isoformat()
        self.monitor_events.put(("update_result", (rel, checked_at), 0))

    def _handle_update_result(self, result):
        rel, checked_at = result
        self.cfg["last_update_check"] = checked_at
        try:
            utils.save_json(config.CONFIG_PATH, self.cfg)
        except (OSError, TypeError, ValueError) as exc:
            messagebox.showerror(
                "Не удалось сохранить проверку обновлений",
                str(exc),
                parent=self,
            )
        if rel:
            self._show_update(rel)

    def _show_update(self, rel):
        notify.notify(f"Доступная новая версия: {rel['tag']}")
        if messagebox.askyesno("Обновление",
                               f"Вышла версия {rel['tag']}.\nОткрыть страницу загрузки?"):
            updater.open_release(rel["url"])

    # ---------- скан и предпросмотр ----------
    def scan(self):
        self._set_active_nav("scan")
        self.status.configure(text="Сканирую…")
        self.update_idletasks()
        self.actions = []
        self.btn_apply.configure(state="disabled", text="Применить (0)")
        self._show_empty_state()
        try:
            self.actions = build_actions(self.cfg, self.history)
        except (OSError, TypeError, ValueError) as exc:
            self.status.configure(text="Не удалось безопасно подготовить предпросмотр.")
            self.scan_summary.configure(text="Сканирование не удалось")
            self._refresh_stats()
            messagebox.showerror("Ошибка предпросмотра", str(exc), parent=self)
            self.after_idle(self.show_next_screenshot_preview)
            return
        self.last_scan = datetime.now()
        if not self.actions:
            self.status.configure(text="Порядок: действий нет.")
            self.scan_summary.configure(
                text=f"Последняя проверка: сегодня в {self.last_scan:%H:%M} · новых действий нет"
            )
            self._refresh_stats()
            self._render_actions()
            self.after_idle(self.show_next_screenshot_preview)
            return
        for a in self.actions:
            a["var"] = ctk.BooleanVar(value=True)
        self._render_actions()
        self.refresh_count()
        self.scan_summary.configure(
            text=f"Последняя проверка: сегодня в {self.last_scan:%H:%M} · найдено {len(self.actions)} объектов"
        )
        self.status.configure(
            text="Проверь выбранные действия — ничего не изменится без подтверждения."
        )

    def refresh_count(self):
        n = sum(1 for a in self.actions if a["var"].get())
        self.btn_apply.configure(
            state="normal" if n else "disabled", text=f"Применить ({n})",
        )
        self._refresh_stats()

    def update_app_category(self, action: dict, category: str):
        if category not in action["category_options"]:
            return
        reserved = {
            other["dst"]
            for other in self.actions
            if other is not action and other["kind"] in {"alias", "alias_move"}
        }
        destination = organization.app_destination(
            config.APPS_ROOT,
            category,
            apps.get_app_name(action["src"]),
            pt.IS_MAC,
            pt.IS_LINUX,
        )
        if action["kind"] == "alias_move" and destination == action["src"]:
            action["dst"] = destination
            action["_category"] = category
            action["_auto_unchecked"] = action["var"].get()
            action["var"].set(False)
            action["desc"] = f"Ярлык уже находится в категории «{category}»: {destination}"
            for label in action.get("_labels", []):
                label.configure(text=f"Уже в «{category}»")
            self.refresh_count()
            return
        if (
            destination.exists()
            or destination.is_symlink()
            or str(destination).casefold()
            in {str(item).casefold() for item in reserved}
        ):
            destination = unique_destination(destination, reserved)
        action["dst"] = destination
        action["_category"] = category
        if action.pop("_auto_unchecked", False):
            action["var"].set(True)
        verb = "Переместить ярлык" if action["kind"] == "alias_move" else "Создать ярлык"
        action["desc"] = f"{verb}: {action['src']}  →  {destination}"
        for label in action.get("_labels", []):
            label.configure(text=f"→ {destination.parent.name}")
        self.refresh_count()

    # ---------- применение и откат ----------
    def apply(self):
        n = sum(1 for a in self.actions if a["var"].get())
        if n == 0:
            return
        if not messagebox.askyesno("Подтверждение", f"Выполнить действий: {n}?"):
            return
        try:
            done = apply_actions(self.actions, self.history, self.cfg)
        except (OSError, TypeError, ValueError) as exc:
            messagebox.showerror("Ошибка применения", str(exc), parent=self)
            return
        self.actions = []
        self._show_empty_state()
        self._refresh_stats()
        self.btn_apply.configure(state="disabled", text="Применить (0)")
        self.scan_summary.configure(text="Сканирование завершено")
        if done == n:
            self.status.configure(text=f"Готово: выполнено {done} действий.")
            notify.notify(f"Уборка завершена: выполнено действий — {done}")
        else:
            self.status.configure(
                text=f"Выполнено {done} из {n}. Ошибки показаны отдельно; "
                "проверь список после нового сканирования."
            )
        self.after_idle(self.show_next_screenshot_preview)

    def queue_screenshot_review(self, path: Path):
        if (
            not organization.is_excluded_path(path, config.EXCLUDED_FOLDERS)
            and shots.is_screenshot(path)
            and path not in self.pending_shots
        ):
            self.pending_shots.append(path)
        self.show_next_screenshot_preview()

    def show_next_screenshot_preview(self):
        if self.actions or (
            self.shot_preview_window and self.shot_preview_window.winfo_exists()
        ):
            return
        while self.pending_shots and not shots.is_screenshot(self.pending_shots[0]):
            self.pending_shots.pop(0)
        if not self.pending_shots:
            return

        source = self.pending_shots.pop(0)
        try:
            apply_folder_names(self.cfg)
        except (OSError, TypeError, ValueError) as exc:
            messagebox.showerror("Ошибка пути", str(exc), parent=self)
            self.after_idle(self.show_next_screenshot_preview)
            return
        destination = utils.unique_dst(
            utils.safe_child_path(config.MUSOR, shots.build_name(source, "", ""))
        )
        win = ctk.CTkToplevel(self)
        self.shot_preview_window = win
        win.title("Предпросмотр нового скриншота")
        win.geometry("700x220")
        win.transient(self)
        win.grab_set()
        ctk.CTkLabel(
            win,
            text=f"Разрешить перемещение?\n\n{source}\n→ {destination}",
            justify="left",
            wraplength=660,
        ).pack(fill="both", expand=True, padx=18, pady=16)

        def finish(allow: bool) -> None:
            if allow and messagebox.askyesno(
                "Подтверждение",
                f"Переместить файл?\n{source}\n→ {destination}",
                parent=win,
            ):
                try:
                    apply_folder_names(self.cfg)
                    if not shots.is_screenshot(source):
                        raise FileNotFoundError(f"Скриншот больше не доступен: {source}")
                    if organization.is_excluded_path(
                        source, config.EXCLUDED_FOLDERS
                    ) or organization.is_excluded_path(
                        destination, config.EXCLUDED_FOLDERS
                    ):
                        raise ValueError(
                            "Скриншот или его назначение попадает в защищённую папку."
                        )
                    validate_action_source(
                        source,
                        [config.DESKTOP, config.MUSOR],
                        direct_child=True,
                    )
                    relative_destination = destination.relative_to(config.MUSOR)
                    if utils.safe_child_path(
                        config.MUSOR, *relative_destination.parts
                    ) != destination:
                        raise ValueError(
                            f"Путь назначения изменился после предпросмотра: {destination}"
                        )
                    if destination.exists() or destination.is_symlink():
                        raise FileExistsError(f"Путь назначения уже занят: {destination}")
                    utils.logged_move(source, destination, self.history, allow_unique=False)
                    self.status.configure(text=f"Перемещён скриншот: {source.name}")
                except (OSError, ValueError) as exc:
                    messagebox.showerror("Ошибка перемещения", str(exc), parent=win)
            elif not allow:
                self.status.configure(text=f"Перемещение отменено: {source.name}")
            win.destroy()
            self.shot_preview_window = None
            self.after_idle(self.show_next_screenshot_preview)

        buttons = ctk.CTkFrame(win, fg_color="transparent")
        buttons.pack(fill="x", padx=14, pady=(0, 12))
        ctk.CTkButton(
            buttons,
            text="Разрешить перемещение",
            command=lambda: finish(True),
        ).pack(side="left")
        ctk.CTkButton(
            buttons,
            text="Оставить на месте",
            fg_color="#7a3b3b",
            command=lambda: finish(False),
        ).pack(side="right")
        win.protocol("WM_DELETE_WINDOW", lambda: finish(False))

    def undo(self):
        reversible = [entry for entry in reversed(self.history) if can_rollback(entry)]
        unavailable = [
            entry for entry in self.history
            if not entry.get("undone")
            and entry.get("action") in {"move", "trash", "alias", "alias_move"}
            and not can_rollback(entry)
        ]
        if not reversible:
            messagebox.showinfo(
                "Откат",
                "Нет доступных для отката действий. Файлы из старых записей, "
                "отправленные в системную Корзину, можно восстановить оттуда.",
            )
            return

        win = ctk.CTkToplevel(self)
        win.title("Выбор действий для отката")
        win.geometry("760x520")
        win.transient(self)
        win.grab_set()
        ctk.CTkLabel(
            win,
            text="Отметь действия для выборочного отката или откати все доступные.",
            anchor="w",
        ).pack(fill="x", padx=14, pady=(14, 6))
        if unavailable:
            ctk.CTkLabel(
                win,
                text=f"{len(unavailable)} старых действий не содержат данных для "
                "безопасного отката; файлы из системной Корзины восстанови вручную.",
                anchor="w",
                text_color="#e0b060",
            ).pack(fill="x", padx=14, pady=4)
        rows = ctk.CTkScrollableFrame(win, label_text="История действий")
        rows.pack(fill="both", expand=True, padx=14, pady=6)
        choices = []
        for entry in reversible:
            selected = ctk.BooleanVar(value=False)
            row = ctk.CTkFrame(rows, fg_color="transparent")
            row.pack(fill="x", padx=8, pady=3)
            ctk.CTkCheckBox(
                row,
                text="",
                variable=selected,
                width=24,
            ).pack(side="left", padx=(0, 6))
            ctk.CTkLabel(
                row,
                text=f"{entry.get('ts', '')}  |  {describe_history_entry(entry)}",
                justify="left",
                anchor="w",
                wraplength=670,
            ).pack(side="left", fill="x", expand=True)
            choices.append((entry, selected))

        def rollback(selected_entries: list[dict]) -> None:
            if not selected_entries:
                messagebox.showwarning("Откат", "Не выбрано ни одного действия.", parent=win)
                return
            if not messagebox.askyesno(
                "Подтверждение отката",
                f"Откатить действий: {len(selected_entries)}?\n"
                "Файлы не будут перезаписаны, если исходное место занято.",
                parent=win,
            ):
                return
            try:
                state = utils.load_json(config.STATE_PATH, {"processed": []})
                if (
                    not isinstance(state, dict)
                    or not isinstance(state.get("processed", []), list)
                    or any(not isinstance(item, str) for item in state.get("processed", []))
                ):
                    raise ValueError("Файл состояния приложения имеет неверный формат.")
                state.setdefault("processed", [])
                count, errors = utils.rollback_entries(
                    self.history,
                    selected_entries,
                    state,
                    config.ROLLBACK_DIR,
                    {
                        "move_sources": [
                            config.DESKTOP,
                            config.DOWNLOADS,
                            config.MUSOR,
                            *map(Path, self.cfg["managed_roots"]["screenshots"]),
                        ],
                        "move_destinations": [
                            config.DESKTOP,
                            config.QUARANTINE_DIR,
                            config.MUSOR,
                            config.FILES_ROOT,
                            *map(Path, self.cfg["managed_roots"]["screenshots"]),
                            *map(Path, self.cfg["managed_roots"]["files"]),
                        ],
                        "alias_destinations": [
                            config.APPS_ROOT,
                            organization.default_locations(
                                config.DESKTOP, self.cfg["folders"]
                            )["apps"],
                            *map(Path, self.cfg["managed_roots"]["apps"]),
                        ],
                        "rollback_roots": [config.DATA_DIR],
                    },
                    excluded_folders=config.EXCLUDED_FOLDERS,
                )
                utils.save_json(config.HISTORY_PATH, self.history)
                utils.save_json(config.STATE_PATH, state)
            except (OSError, TypeError, ValueError) as exc:
                messagebox.showerror("Ошибка отката", str(exc), parent=win)
                return
            self.status.configure(text=f"Откат: выполнено действий — {count}.")
            win.destroy()
            if errors:
                messagebox.showwarning(
                    "Частичный откат",
                    f"Выполнено: {count}. Не удалось: {len(errors)}.\n\n"
                    + "\n".join(errors[:8]),
                    parent=self,
                )
            else:
                messagebox.showinfo("Откат", f"Откат выполнен: {count} действий.", parent=self)

        buttons = ctk.CTkFrame(win, fg_color="transparent")
        buttons.pack(fill="x", padx=14, pady=(6, 14))
        ctk.CTkButton(
            buttons,
            text="Откатить выбранное",
            command=lambda: rollback(
                [entry for entry, selected in choices if selected.get()]
            ),
        ).pack(side="left")
        ctk.CTkButton(
            buttons,
            text="Откатить все доступные",
            fg_color="#7a3b3b",
            command=lambda: rollback(reversible),
        ).pack(side="right")

    # ---------- мониторинг ----------
    def toggle_watch(self):
        enabled = bool(self.mon.get())
        previous = self.cfg["background_monitoring"]
        if enabled and not previous and not messagebox.askyesno(
            "Разрешить фоновый мониторинг",
            "DesktopKeeper будет наблюдать только существующие стандартные папки "
            "рабочего стола, загрузок и приложений, которые не защищены в настройках.\n\n"
            "Приложение не может гарантировать обнаружение всех установок. "
            "Мониторинг не перемещает файлы без твоего подтверждения; таймер "
            "установщиков — отдельная настройка.\n\nВключить мониторинг?",
            parent=self,
        ):
            self.mon.deselect()
            return
        self.cfg["background_monitoring"] = enabled
        try:
            utils.save_json(config.CONFIG_PATH, self.cfg)
            if enabled:
                observer = Observer()
                watched = set()
                screenshot_roots = dict.fromkeys(
                    folder.resolve()
                    for folder in (config.DESKTOP, config.MUSOR)
                    if folder.is_dir()
                    and not organization.is_excluded_path(
                        folder, config.EXCLUDED_FOLDERS
                    )
                )
                for folder in screenshot_roots:
                    observer.schedule(
                        ShotWatcher(
                            lambda p: self.monitor_events.put(
                                ("screenshot", p, 0)
                            )
                        ),
                        str(folder),
                        recursive=False,
                    )
                    watched.add(folder)

                app_roots = [
                    folder
                    for folder in config.APP_DIRS
                    if folder.is_dir()
                    and not organization.is_excluded_path(
                        folder, config.EXCLUDED_FOLDERS
                    )
                ]
                activity_handler = ActivityWatcher(
                    app_roots,
                    config.DOWNLOADS,
                    lambda p: self.monitor_events.put(
                        ("application", p, monotonic() + 2.5)
                    ),
                    lambda p: self.monitor_events.put(
                        ("installer", p, monotonic() + 1.5)
                    ),
                )
                for folder in safe_watch_directories(app_roots):
                    if folder.resolve() not in watched:
                        observer.schedule(
                            activity_handler, str(folder), recursive=False
                        )
                        watched.add(folder.resolve())
                if (
                    config.DOWNLOADS.is_dir()
                    and not organization.is_excluded_path(
                        config.DOWNLOADS, config.EXCLUDED_FOLDERS
                    )
                    and config.DOWNLOADS.resolve() not in watched
                ):
                    observer.schedule(
                        activity_handler, str(config.DOWNLOADS), recursive=False
                    )
                    watched.add(config.DOWNLOADS.resolve())
                if not watched:
                    raise ValueError(
                        "Нет доступных папок для мониторинга. "
                        "Новые папки не создавались."
                    )
                observer.start()
                self.observer = observer
            elif self.observer:
                self.observer.stop()
                self.observer.join(timeout=5)
                self.observer = None
            self.monitor_status.configure(
                text=(
                    "●  Мониторинг активен" if enabled
                    else "●  Мониторинг выключен"
                ),
                text_color="#36A853" if enabled else MUTED,
            )
            self.status.configure(
                text="Мониторинг включён." if enabled else "Мониторинг выключен."
            )
        except (OSError, TypeError, ValueError, RuntimeError) as exc:
            if self.observer:
                self.observer.stop()
                self.observer.join(timeout=5)
                self.observer = None
            self.cfg["background_monitoring"] = previous
            self.mon.select() if previous else self.mon.deselect()
            try:
                utils.save_json(config.CONFIG_PATH, self.cfg)
            except (OSError, TypeError, ValueError) as save_error:
                logger.exception("Не удалось сохранить состояние мониторинга")
                messagebox.showerror(
                    "Не удалось сохранить настройку мониторинга",
                    str(save_error),
                    parent=self,
                )
            messagebox.showerror("Ошибка мониторинга", str(exc), parent=self)

    def close(self):
        if self.observer:
            self.observer.stop()
            self.observer.join(timeout=5)
            self.observer = None
        self.destroy()

    def toggle_autostart(self):
        enabling = bool(self.auto.get())
        try:
            if enabling:
                autostart.enable()
                self.status.configure(text="Автозапуск включён.")
            else:
                autostart.disable()
                self.status.configure(text="Автозапуск выключен.")
        except (OSError, ValueError, subprocess.SubprocessError) as exc:
            if enabling:
                self.auto.deselect()
            else:
                self.auto.select()
            messagebox.showerror("Ошибка автозапуска", str(exc), parent=self)

    # ---------- категории и справка ----------
    def edit_categories(self):
        win = ctk.CTkToplevel(self)
        win.title("Категории")
        win.geometry("420x480")
        lb = ctk.CTkScrollableFrame(win, label_text="Существующие категории")
        lb.pack(fill="both", expand=True, padx=12, pady=(12, 6))
        rows = {}
        for name in self.cfg["categories"]:
            rows[name] = ctk.CTkLabel(lb, text=name, anchor="w")
            rows[name].pack(fill="x", padx=8, pady=2)

        def refresh():
            for w in lb.winfo_children():
                w.destroy()
            rows.clear()
            for name in self.cfg["categories"]:
                ctk.CTkLabel(lb, text=name, anchor="w").pack(fill="x", padx=8, pady=2)

        bar = ctk.CTkFrame(win, fg_color="transparent")
        bar.pack(fill="x", padx=12, pady=6)
        ent = ctk.CTkEntry(bar, placeholder_text="новая категория")
        ent.pack(side="left", fill="x", expand=True)

        def add():
            name = ent.get().strip()
            if not name:
                return
            try:
                folder = cats.add_category(name)
            except (OSError, ValueError) as exc:
                messagebox.showerror("Не удалось создать категорию", str(exc), parent=win)
                return
            self.cfg["categories"].setdefault(folder.name, [])
            utils.save_json(config.CONFIG_PATH, self.cfg)
            ent.delete(0, "end")
            refresh()

        def remove():
            sel = ent.get().strip()
            if sel in self.cfg["categories"]:
                if sel == "Другое":
                    messagebox.showwarning(
                        "Категория защищена",
                        "Категорию «Другое» нельзя удалить.",
                        parent=win,
                    )
                    return
                if not messagebox.askyesno(
                    "Удалить категорию",
                    f"Удалить «{sel}» из доступных категорий?\n"
                    "Уже созданные ярлыки и файлы останутся на месте.",
                    parent=win,
                ):
                    return
                del self.cfg["categories"][sel]
                self.cfg["app_categories"] = {
                    app: category
                    for app, category in self.cfg["app_categories"].items()
                    if category != sel
                }
                utils.save_json(config.CONFIG_PATH, self.cfg)
                refresh()

        ctk.CTkButton(bar, text="+", width=40, command=add).pack(side="left", padx=4)
        ctk.CTkButton(bar, text="−", width=40, fg_color="#7a3b3b",
                      command=remove).pack(side="left")
        ctk.CTkLabel(win, text="«+» создать, «−» удалить (имя в поле ввода)",
                     font=("", 11), text_color="#9a9a9a").pack(pady=(0, 10))

    def edit_app_assignments(self):
        try:
            installed = apps.scan_applications()
        except OSError as exc:
            messagebox.showerror("Сканирование приложений", str(exc), parent=self)
            return
        if not installed:
            messagebox.showinfo("Приложения", "Установленные приложения не найдены.", parent=self)
            return

        aliases = organization.active_aliases(self.history)
        win = ctk.CTkToplevel(self)
        win.title("Категории приложений")
        win.geometry("760x560")
        win.transient(self)
        win.grab_set()
        ctk.CTkLabel(
            win,
            text="Выбери папку для каждого приложения. Перемещения появятся в предпросмотре.",
            anchor="w",
            wraplength=700,
        ).pack(fill="x", padx=14, pady=(14, 8))
        rows = ctk.CTkScrollableFrame(win, label_text="Найденные приложения")
        rows.pack(fill="both", expand=True, padx=14, pady=6)
        assignments = {}
        categories = list(self.cfg["categories"])
        for app in installed:
            name = apps.get_app_name(app)
            bundle_id = apps.get_bundle_id(app)
            previous = aliases.get(str(app.resolve()))
            selected = (
                self.cfg["app_categories"].get(bundle_id)
                or self.cfg["app_categories"].get(name)
                or ((previous or {}).get("category"))
                or apps.find_category(name, bundle_id, self.cfg["categories"])
                or "Другое"
            )
            if selected not in categories:
                selected = "Другое"
            row = ctk.CTkFrame(rows, fg_color="transparent")
            row.pack(fill="x", padx=8, pady=3)
            ctk.CTkLabel(
                row, text=name, width=190, anchor="w"
            ).pack(side="left", padx=(0, 8))
            ctk.CTkLabel(
                row, text=str(app), anchor="w", text_color="#9a9a9a"
            ).pack(side="left", fill="x", expand=True, padx=(0, 8))
            variable = ctk.StringVar(value=selected)
            ctk.CTkOptionMenu(
                row, values=categories, variable=variable, width=150
            ).pack(side="right")
            assignments[bundle_id or name] = variable

        def save():
            for name, variable in assignments.items():
                self.cfg["app_categories"][name] = variable.get()
            try:
                utils.save_json(config.CONFIG_PATH, self.cfg)
            except (OSError, TypeError, ValueError) as exc:
                messagebox.showerror("Ошибка сохранения", str(exc), parent=win)
                return
            win.destroy()
            self.status.configure(
                text="Назначения сохранены. Нажми «Сканировать систему», чтобы увидеть перемещения."
            )

        buttons = ctk.CTkFrame(win, fg_color="transparent")
        buttons.pack(fill="x", padx=14, pady=(6, 14))
        ctk.CTkButton(buttons, text="Сохранить назначения", command=save).pack(side="left")
        ctk.CTkButton(
            buttons, text="Отмена", fg_color="#3a3a3a", command=win.destroy
        ).pack(side="right")

    def show_help(self):
        win = ctk.CTkToplevel(self)
        win.title("Справка")
        win.geometry("560x520")
        tb = ctk.CTkTextbox(win, wrap="word")
        tb.pack(fill="both", expand=True, padx=12, pady=12)
        tb.insert("0.0", HELP_TEXT)
        tb.configure(state="disabled")


def start_main(scan_now: bool = False):
    try:
        cfg = load_cfg()
        apply_folder_names(cfg)
        history = utils.load_json(config.HISTORY_PATH, [])
        if not isinstance(history, list) or any(
            not isinstance(entry, dict) for entry in history
        ):
            raise ValueError("История действий должна быть списком JSON-объектов.")
        app = Main(cfg, history)
    except (OSError, TypeError, ValueError) as exc:
        root = ctk.CTk()
        root.withdraw()
        messagebox.showerror(
            "Не удалось запустить DesktopKeeper",
            f"Проверь настройки и историю действий:\n{exc}",
            parent=root,
        )
        root.destroy()
        return
    if scan_now:
        app.after(300, app.scan)
    app.mainloop()


if __name__ == "__main__":
    try:
        cfg = load_cfg()
        apply_folder_names(cfg)
    except (OSError, TypeError, ValueError) as exc:
        root = ctk.CTk()
        root.withdraw()
        messagebox.showerror(
            "Не удалось запустить DesktopKeeper",
            f"Проверь настройки приложения:\n{exc}",
            parent=root,
        )
        root.destroy()
        raise SystemExit(1)
    if not cfg["onboarding_done"]:
        Wizard(cfg, on_finish=lambda scan_now=False: start_main(scan_now)).mainloop()
    else:
        start_main()