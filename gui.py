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
from functools import partial
from pathlib import Path

import customtkinter as ctk
from tkinter import messagebox
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

import app_handler as apps
import categories as cats
import config
import file_sorter as sorter
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
    cfg.setdefault("enabled_types", list(sorter.TYPE_MAP.keys()) + ["Другое"])
    cfg.setdefault("folders", {"musor": "мусор", "apps": "Apps", "files": "Файлы"})
    cfg.setdefault("onboarding_done", False)
    if not isinstance(cfg["categories"], dict):
        raise ValueError("Настройка категорий должна быть JSON-объектом.")
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
    return cfg


def apply_folder_names(cfg: dict) -> None:
    f = cfg["folders"]
    config.MUSOR = utils.safe_child_path(config.DESKTOP, f["musor"])
    config.APPS_ROOT = utils.safe_child_path(config.DESKTOP, f["apps"])
    config.FILES_ROOT = utils.safe_child_path(config.DESKTOP, f["files"])


def reserve_destination(path: Path, reserved: set[Path]) -> Path:
    return utils.unique_dst(path, reserved)


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


def build_actions(cfg: dict) -> list[dict]:
    """Один проход по системе: собираем список предлагаемых действий."""
    actions: list[dict] = []
    reserved: set[Path] = set()
    feat = cfg["features"]

    if feat["screenshots"]:
        for f in shots.collect():
            dst = reserve_destination(config.MUSOR / shots.build_name(f, "", ""), reserved)
            if f == dst:
                continue
            actions.append({
                "kind": "move", "src": f, "dst": dst,
                "desc": f"Переместить скриншот: {f}  →  {dst}",
            })

    if feat["sort_files"]:
        enabled = set(cfg["enabled_types"])
        for f, t in sorter.collect():
            if t not in enabled:
                continue
            dst = reserve_destination(config.FILES_ROOT / t / f.name, reserved)
            actions.append({
                "kind": "move", "src": f, "dst": dst,
                "desc": f"Переместить: {f}  →  {dst}",
            })

    if feat["apps"]:
        state = utils.load_json(config.STATE_PATH, {"processed": []})
        if not isinstance(state, dict) or not isinstance(state.get("processed", []), list):
            raise ValueError("Файл состояния приложения имеет неверный формат.")
        for app in apps.scan_applications():
            name = apps.get_app_name(app)
            bid = apps.get_bundle_id(app)
            if name in state["processed"] or (bid and bid in state["processed"]):
                continue
            cat = apps.find_category(name, bid, cfg["categories"])
            if not cat:
                cat = "Утилиты"
            dst = utils.safe_child_path(config.APPS_ROOT, cat, app.stem)
            actual_dst = dst.with_suffix(".lnk") if not pt.IS_MAC else dst
            if actual_dst.exists() or actual_dst.is_symlink() or actual_dst in reserved:
                continue
            reserved.add(actual_dst)
            actions.append({"kind": "alias", "src": app, "_bid": bid,
                            "app": name, "dst": dst,
                            "desc": f"Создать ярлык: {app}  →  {actual_dst}"})

    if feat["installers"]:
        app_names = {apps.get_app_name(a).lower() for a in apps.scan_applications()}
        for ins in apps.scan_downloads():
            n = ins.stem.lower()
            if any(n in a or a in n for a in app_names):
                dst = reserve_destination(config.QUARANTINE_DIR / ins.name, reserved)
                actions.append({"kind": "trash", "src": ins, "dst": dst,
                                "desc": f"Переместить установщик: {ins}  →  {dst}"})
    return actions


def apply_actions(actions: list[dict], history: list) -> int:
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
                actual_dst = a["dst"].with_suffix(".lnk") if not pt.IS_MAC else a["dst"]
                if actual_dst.exists() or actual_dst.is_symlink():
                    raise FileExistsError(f"Ярлык уже существует: {actual_dst}. Выполни новое сканирование.")
                real = pt.create_shortcut(a["src"], a["dst"])
                state["processed"].append(a.get("app", a["src"].stem))
                if a.get("_bid"):
                    state["processed"].append(a["_bid"])
                history.append({
                    "ts": now(), "action": "alias", "src": str(src),
                    "dst": str(real), "app": a.get("app", a["src"].stem),
                    "bundle_id": a.get("_bid"), "batch": batch,
                })
                utils.save_json(config.HISTORY_PATH, history)
                utils.save_json(config.STATE_PATH, state)
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
    if entry.get("action") in {"move", "trash"}:
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
Кнопка «Категории» — добавляй и удаляй папки-категории
для ярлыков приложений. Новое приложение без категории:
приложение спросит, куда его положить, и запомнит ответ.

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
        for k in self.cfg["features"]:
            self.cfg["features"][k] = self.vars[f"feat_{k}"].get()
        self.cfg["enabled_types"] = [t for t in list(sorter.TYPE_MAP.keys()) + ["Другое"]
                                     if self.vars[f"type_{t}"].get()]
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
            for t in list(sorter.TYPE_MAP.keys()) + ["Другое"]:
                v = ctk.BooleanVar(value=t in self.cfg["enabled_types"])
                ctk.CTkCheckBox(box, text=t, variable=v).pack(anchor="w", padx=16, pady=2)
                self.vars[f"type_{t}"] = v
            self.nav()
        else:
            ctk.CTkLabel(self.frame, text="Всё готово", font=("", 26, "bold")).pack(pady=(40, 8))
            ctk.CTkLabel(self.frame, justify="left", font=("", 14), text=(
                f"Папки: {self.cfg['folders']['musor']}, {self.cfg['folders']['apps']}, "
                f"{self.cfg['folders']['files']} (создадутся сами).\n\n"
                "Нажми «Начать сканирование» — я один раз пройду по системе\n"
                "и покажу, что и куда предлагаю переместить.")).pack(padx=30)
            self.nav(last=True)


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
        ctk.CTkButton(mid, text="Справка", width=90, fg_color="#3a3a3a",
                      command=self.show_help).pack(side="right")

        self.status = ctk.CTkLabel(self, text="Нажми «Сканировать систему»", anchor="w")
        self.status.pack(fill="x", padx=16, pady=(6, 2))

        self.list = ctk.CTkScrollableFrame(self, label_text="Предлагаемые действия")
        self.list.pack(fill="both", expand=True, padx=14, pady=(4, 14))
        self.after(1500, self.schedule_update_check)

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
            self.actions = build_actions(self.cfg)
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
        self.refresh_count()
        self.status.configure(text=f"Подготовлено действий: {len(self.actions)}. Проверь отдельное окно предпросмотра.")
        self.show_preview()

    def refresh_count(self):
        n = sum(1 for a in self.actions if a["var"].get())
        self.btn_apply.configure(state="normal" if n else "disabled",
                                 text=f"Предпросмотр действий ({n})")
        if self.preview_apply_btn:
            self.preview_apply_btn.configure(state="normal" if n else "disabled")

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
            ctk.CTkLabel(
                row,
                text=action["desc"],
                justify="left",
                anchor="w",
                wraplength=670,
            ).pack(side="left", fill="x", expand=True)
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
            done = apply_actions(self.actions, self.history)
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
        destination = utils.unique_dst(
            config.MUSOR / shots.build_name(source, "", "")
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
                    if not shots.is_screenshot(source):
                        raise FileNotFoundError(f"Скриншот больше не доступен: {source}")
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
            and entry.get("action") in {"move", "trash", "alias"}
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
                        "move_sources": [config.DESKTOP, config.DOWNLOADS],
                        "move_destinations": [config.DESKTOP, config.QUARANTINE_DIR],
                        "alias_destinations": [config.APPS_ROOT],
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
            for folder in (config.DESKTOP, config.MUSOR):
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
                del self.cfg["categories"][sel]
                utils.save_json(config.CONFIG_PATH, self.cfg)
                refresh()

        ctk.CTkButton(bar, text="+", width=40, command=add).pack(side="left", padx=4)
        ctk.CTkButton(bar, text="−", width=40, fg_color="#7a3b3b",
                      command=remove).pack(side="left")
        ctk.CTkLabel(win, text="«+» создать, «−» удалить (имя в поле ввода)",
                     font=("", 11), text_color="#9a9a9a").pack(pady=(0, 10))

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