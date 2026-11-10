"""DesktopKeeper GUI: онбординг, опросник, скан с предпросмотром.
Запуск: python3 gui.py
"""
from __future__ import annotations

import updater
import autostart
import notify
import subprocess
import threading
import uuid
from datetime import datetime
from pathlib import Path

import customtkinter as ctk
from tkinter import filedialog, messagebox
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

import app_handler as apps
import categories as cats
import config
import file_sorter as sorter
import organization
import platform_tools as pt
import screenshot_handler as shots
import utils

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

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
    cfg.setdefault("categories", dict(DEFAULT_CATEGORIES))
    default_features = {
        "screenshots": True,
        "sort_files": True,
        "apps": True,
        "installers": True,
    }
    cfg.setdefault("features", dict(default_features))
    cfg.setdefault("folders", {"musor": "мусор", "apps": "Apps", "files": "Файлы"})
    cfg.setdefault("layout_mode", "automatic")
    cfg.setdefault("locations", {})
    cfg.setdefault("managed_roots", {key: [] for key in organization.LOCATION_KEYS})
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
        self.geometry("760x720")
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
            self, text="Куда раскладывать", font=("", 18, "bold")
        ).pack(anchor="w", padx=16, pady=(14, 6))
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
            dst = reserve_destination(
                utils.safe_child_path(config.MUSOR, shots.build_name(f, "", "")),
                reserved,
            )
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
            if t not in enabled:
                continue
            dst = reserve_destination(
                utils.safe_child_path(config.FILES_ROOT, t, f.name), reserved
            )
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
                config.APPS_ROOT, cat, app.stem, pt.IS_MAC
            )
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
                direct_child=a["kind"] != "alias_move",
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
Включи тумблер «Мониторинг» — новые скриншоты будут
показаны в отдельном окне; перемещение произойдёт только после разрешения.

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
                f"{self.cfg['folders']['files']} (создадутся сами).\n\n"
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
        self.preview_window = None
        self.preview_apply_btn = None
        self.pending_shots: list[Path] = []
        self.shot_preview_window = None
        self.title("DesktopKeeper")
        self.geometry("760x620")

        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", padx=14, pady=(14, 6))
        self.btn_scan = ctk.CTkButton(top, text="Сканировать систему", command=self.scan)
        self.btn_scan.pack(side="left")
        ToolTip(self.btn_scan, "Один проход по рабочему столу, загрузкам и приложениям:\nпокажу список действий с галочками")
        self.btn_apply = ctk.CTkButton(top, text="Предпросмотр действий (0)",
                                       state="disabled", command=self.show_preview)
        self.btn_apply.pack(side="left", padx=8)
        ToolTip(self.btn_apply, "Открой список действий, выбери разрешённые и подтверди применение")
        self.btn_undo = ctk.CTkButton(top, text="Откатить действия",
                                      fg_color="#7a3b3b", command=self.undo)
        self.btn_undo.pack(side="left")
        ToolTip(self.btn_undo, "Выбери отдельные действия или откати все доступные изменения")

        mid = ctk.CTkFrame(self, fg_color="transparent")
        mid.pack(fill="x", padx=14)
        self.mon = ctk.CTkSwitch(mid, text="Мониторинг скринов", command=self.toggle_watch)
        self.mon.pack(side="left")
        ToolTip(self.mon, "Для каждого нового скриншота сначала показывается запрос на перемещение")
        self.auto = ctk.CTkSwitch(mid, text="Автозапуск", command=self.toggle_autostart)
        self.auto.pack(side="left", padx=12)
        if autostart.is_enabled():
            self.auto.select()
        ToolTip(self.auto, "Запускать DesktopKeeper при входе в систему")
        ctk.CTkButton(mid, text="Категории", width=100, fg_color="#3a3a3a",
                      command=self.edit_categories).pack(side="right", padx=4)
        ctk.CTkButton(
            mid,
            text="Папки и типы",
            width=115,
            fg_color="#3a3a3a",
            command=lambda: SettingsWindow(self, self.cfg, self.settings_saved),
        ).pack(side="right", padx=4)
        ctk.CTkButton(
            mid,
            text="Приложения",
            width=100,
            fg_color="#3a3a3a",
            command=self.edit_app_assignments,
        ).pack(side="right", padx=4)
        ctk.CTkButton(mid, text="Справка", width=90, fg_color="#3a3a3a",
                      command=self.show_help).pack(side="right")

        self.status = ctk.CTkLabel(self, text="Нажми «Сканировать систему»", anchor="w")
        self.status.pack(fill="x", padx=16, pady=(6, 2))

        self.list = ctk.CTkScrollableFrame(self, label_text="Предлагаемые действия")
        self.list.pack(fill="both", expand=True, padx=14, pady=(4, 14))
        self.after(1500, self.schedule_update_check)

    def settings_saved(self):
        self.status.configure(text="Настройки сохранены. Новые назначения будут показаны при следующем сканировании.")

    def schedule_update_check(self):
        today = datetime.now().date().isoformat()
        if self.cfg.get("last_update_check") == today:
            return
        threading.Thread(target=self._update_check, daemon=True).start()

    def _update_check(self):
        rel = updater.check_update()
        self.cfg["last_update_check"] = datetime.now().date().isoformat()
        utils.save_json(config.CONFIG_PATH, self.cfg)
        if rel:
            self.after(0, lambda: self._show_update(rel))

    def _show_update(self, rel):
        notify.notify(f"Доступная новая версия: {rel['tag']}")
        if messagebox.askyesno("Обновление",
                               f"Вышла версия {rel['tag']}.\nОткрыть страницу загрузки?"):
            updater.open_release(rel["url"])

    # ---------- скан и предпросмотр ----------
    def scan(self):
        self.status.configure(text="Сканирую…")
        self.update_idletasks()
        self.actions = []
        self.btn_apply.configure(state="disabled", text="Предпросмотр действий (0)")
        for w in self.list.winfo_children():
            w.destroy()
        try:
            self.actions = build_actions(self.cfg, self.history)
        except (OSError, TypeError, ValueError) as exc:
            self.status.configure(text="Не удалось безопасно подготовить предпросмотр.")
            messagebox.showerror("Ошибка предпросмотра", str(exc), parent=self)
            return
        if not self.actions:
            self.status.configure(text="Порядок: действий нет.")
            self.btn_apply.configure(state="disabled", text="Предпросмотр действий (0)")
            return
        for a in self.actions:
            a["var"] = ctk.BooleanVar(value=True)
            ctk.CTkLabel(self.list, text=a["desc"], anchor="w").pack(
                anchor="w", padx=10, pady=3
            )
            a["_labels"] = [self.list.winfo_children()[-1]]
        self.refresh_count()
        self.status.configure(text=f"Подготовлено действий: {len(self.actions)}. Проверь отдельное окно предпросмотра.")
        self.show_preview()

    def refresh_count(self):
        n = sum(1 for a in self.actions if a["var"].get())
        self.btn_apply.configure(state="normal" if n else "disabled",
                                 text=f"Предпросмотр действий ({n})")
        if self.preview_apply_btn:
            self.preview_apply_btn.configure(state="normal" if n else "disabled")

    def update_app_category(self, action: dict, category: str):
        if category not in action["category_options"]:
            return
        reserved = {
            other["dst"]
            for other in self.actions
            if other is not action and other["kind"] in {"alias", "alias_move"}
        }
        destination = organization.app_destination(
            config.APPS_ROOT, category, action["src"].stem, pt.IS_MAC
        )
        if action["kind"] == "alias_move" and destination == action["src"]:
            action["dst"] = destination
            action["_category"] = category
            action["_auto_unchecked"] = action["var"].get()
            action["var"].set(False)
            action["desc"] = f"Ярлык уже находится в категории «{category}»: {destination}"
            for label in action.get("_labels", []):
                label.configure(text=action["desc"])
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
            label.configure(text=action["desc"])
        self.refresh_count()

    def show_preview(self):
        if not self.actions:
            return
        if self.preview_window and self.preview_window.winfo_exists():
            self.preview_window.focus_force()
            return

        win = ctk.CTkToplevel(self)
        self.preview_window = win
        win.title("Предпросмотр действий")
        win.geometry("760x520")
        win.transient(self)
        win.grab_set()
        ctk.CTkLabel(
            win,
            text="Ничего не изменится, пока ты не подтвердишь выбранные действия.",
            anchor="w",
        ).pack(fill="x", padx=14, pady=(14, 6))
        rows = ctk.CTkScrollableFrame(win, label_text="Предлагаемые действия")
        rows.pack(fill="both", expand=True, padx=14, pady=6)
        for action in self.actions:
            row = ctk.CTkFrame(rows, fg_color="transparent")
            row.pack(fill="x", padx=8, pady=3)
            ctk.CTkCheckBox(
                row,
                text="",
                variable=action["var"],
                command=self.refresh_count,
                width=24,
            ).pack(side="left", padx=(0, 6))
            if action["kind"] in {"alias", "alias_move"}:
                ctk.CTkOptionMenu(
                    row,
                    values=action["category_options"],
                    variable=ctk.StringVar(value=action["_category"]),
                    width=150,
                    command=lambda value, selected=action: self.update_app_category(
                        selected, value
                    ),
                ).pack(side="left", padx=(0, 8))
            ctk.CTkLabel(
                row,
                text=action["desc"],
                justify="left",
                anchor="w",
                wraplength=670,
            ).pack(side="left", fill="x", expand=True)
            action.setdefault("_labels", []).append(row.winfo_children()[-1])
        buttons = ctk.CTkFrame(win, fg_color="transparent")
        buttons.pack(fill="x", padx=14, pady=(6, 14))
        self.preview_apply_btn = ctk.CTkButton(
            buttons,
            text="Разрешить выбранное",
            command=self.apply,
        )
        self.preview_apply_btn.pack(side="left")
        ctk.CTkButton(
            buttons,
            text="Запретить всё",
            fg_color="#7a3b3b",
            command=self.cancel_preview,
        ).pack(side="right")
        win.protocol("WM_DELETE_WINDOW", self.cancel_preview)
        self.refresh_count()

    def cancel_preview(self):
        if self.preview_window and self.preview_window.winfo_exists():
            self.preview_window.destroy()
        self.preview_window = None
        self.preview_apply_btn = None
        self.actions = []
        self.btn_apply.configure(state="disabled", text="Предпросмотр действий (0)")
        self.status.configure(text="Отменено. Никакие действия не выполнены.")
        self.after_idle(self.show_next_screenshot_preview)

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
            messagebox.showerror("Ошибка применения", str(exc), parent=self.preview_window or self)
            return
        if self.preview_window and self.preview_window.winfo_exists():
            self.preview_window.destroy()
        self.preview_window = None
        self.preview_apply_btn = None
        self.actions = []
        for w in self.list.winfo_children():
            w.destroy()
        self.btn_apply.configure(state="disabled", text="Предпросмотр действий (0)")
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
        if shots.is_screenshot(path) and path not in self.pending_shots:
            self.pending_shots.append(path)
        self.show_next_screenshot_preview()

    def show_next_screenshot_preview(self):
        if (
            self.preview_window and self.preview_window.winfo_exists()
        ) or (
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
        if self.mon.get():
            def on_shot(p: Path):
                self.after(0, lambda: self.queue_screenshot_review(p))
            self.observer = Observer()
            folders = dict.fromkeys(
                folder.resolve() for folder in (config.DESKTOP, config.MUSOR)
            )
            for folder in folders:
                folder.mkdir(parents=True, exist_ok=True)
                self.observer.schedule(ShotWatcher(on_shot), str(folder), recursive=False)
            self.observer.start()
            self.status.configure(text="Мониторинг включён.")
        elif self.observer:
            self.observer.stop()
            self.observer = None
            self.status.configure(text="Мониторинг выключен.")

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
            folder = cats.add_category(name)
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