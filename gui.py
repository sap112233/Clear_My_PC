"""DesktopKeeper GUI: онбординг, опросник, скан с предпросмотром.
Запуск: python3 gui.py
"""
from __future__ import annotations

import shutil
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
    cfg.setdefault("categories", dict(DEFAULT_CATEGORIES))
    cfg.setdefault("features", {"screenshots": True, "sort_files": True,
                                "apps": True, "installers": True})
    cfg.setdefault("enabled_types", list(sorter.TYPE_MAP.keys()) + ["Другое"])
    cfg.setdefault("folders", {"musor": "мусор", "apps": "Apps", "files": "Файлы"})
    cfg.setdefault("onboarding_done", False)
    return cfg


def apply_folder_names(cfg: dict) -> None:
    f = cfg["folders"]
    config.MUSOR = config.DESKTOP / f["musor"]
    config.APPS_ROOT = config.DESKTOP / f["apps"]
    config.FILES_ROOT = config.DESKTOP / f["files"]


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


def ask_category_dialog(app_name: str, cat_dict: dict) -> str | None:
    win = ctk.CTkToplevel()
    win.title("Новое приложение")
    win.geometry("440x230")
    win.grab_set()
    ctk.CTkLabel(win, text=f"Приложение «{app_name}» не найдено в словаре.\nВ какую категорию положить ярлык?",
                 justify="left").pack(padx=16, pady=(16, 8))
    combo = ctk.CTkComboBox(win, values=list(cat_dict.keys()) + ["— новая категория —"])
    combo.pack(padx=16, pady=4)
    entry = ctk.CTkEntry(win, placeholder_text="имя новой категории (если выбрал её выше)")
    entry.pack(padx=16, pady=4)
    res = {"cat": None}

    def ok():
        choice = combo.get()
        if choice == "— новая категория —":
            name = entry.get().strip()
            if name:
                cats.add_category(name)
                cat_dict[name] = []
                res["cat"] = name
        else:
            res["cat"] = choice
        win.destroy()

    ctk.CTkButton(win, text="ОК", width=120, command=ok).pack(pady=10)
    win.wait_window()
    return res["cat"]


def build_actions(cfg: dict) -> list[dict]:
    """Один проход по системе: собираем список предлагаемых действий."""
    actions: list[dict] = []
    feat = cfg["features"]

    if feat["screenshots"]:
        for f in shots.collect():
            dst = config.MUSOR / shots.build_name(f, "", "")
            actions.append({"kind": "move", "src": f, "dst": dst,
                            "desc": f"Скриншот {f.name}  →  {cfg['folders']['musor']}/{dst.name}"})

    if feat["sort_files"]:
        enabled = set(cfg["enabled_types"])
        for f, t in sorter.collect():
            if t not in enabled:
                continue
            actions.append({"kind": "move", "src": f, "dst": config.FILES_ROOT / t / f.name,
                            "desc": f"{f.name}  →  {cfg['folders']['files']}/{t}/"})

    if feat["apps"]:
        state = utils.load_json(config.STATE_PATH, {"processed": []})
        for app in apps.scan_applications():
            name = apps.get_app_name(app)
            bid = apps.get_bundle_id(app)
            if name in state["processed"] or (bid and bid in state["processed"]):
                continue
            cat = apps.find_category(name, bid, cfg["categories"])
            if not cat:
                cat = ask_category_dialog(name, cfg["categories"]) or "Утилиты"
            actions.append({"kind": "alias", "src": app, "_bid": bid,
                            "dst": config.APPS_ROOT / cat / app.stem,
                            "desc": f"{name}  →  {cfg['folders']['apps']}/{cat}/ (ярлык)"})

    if feat["installers"]:
        app_names = {apps.get_app_name(a).lower() for a in apps.scan_applications()}
        for ins in apps.scan_downloads():
            n = ins.stem.lower()
            if any(n in a or a in n for a in app_names):
                actions.append({"kind": "trash", "src": ins, "dst": None,
                                "desc": f"Установщик {ins.name}  →  Корзина"})
    return actions


def apply_actions(actions: list[dict], history: list) -> int:
    batch = uuid.uuid4().hex
    state = utils.load_json(config.STATE_PATH, {"processed": []})
    done = 0
    for a in actions:
        if not a["var"].get():
            continue
        try:
            if a["kind"] == "move":
                utils.logged_move(a["src"], a["dst"], history)
                history[-1]["batch"] = batch
            elif a["kind"] == "trash":
                if pt.send_to_trash(a["src"]):
                    history.append({"ts": now(), "action": "trash",
                                    "src": str(a["src"]), "batch": batch})
            elif a["kind"] == "alias":
                real = pt.create_shortcut(a["src"], a["dst"])
                state["processed"].append(a["src"].stem)
                if a.get("_bid"):
                    state["processed"].append(a["_bid"])
                history.append({"ts": now(), "action": "alias", "src": str(a["src"]),
                                "dst": str(real), "batch": batch})
            done += 1
        except Exception as e:
            messagebox.showerror("Ошибка", f"{a['src']}\n{e}")
    utils.save_json(config.HISTORY_PATH, history)
    utils.save_json(config.STATE_PATH, state)
    return done


def undo_last(history: list) -> int:
    batches = [h.get("batch") for h in history if h.get("batch")]
    if not batches:
        return 0
    last = batches[-1]
    undone = 0
    keep = []
    for h in history:
        if h.get("batch") == last and h["action"] == "move" and Path(h["dst"]).exists():
            shutil.move(h["dst"], h["src"])
            undone += 1
        else:
            keep.append(h)
    keep.append({"ts": now(), "action": "undo", "undone": undone, "batch": last})
    history[:] = keep
    utils.save_json(config.HISTORY_PATH, history)
    return undone


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

3. Нажми «Применить выбранные».
   Скриншоты уедут в папку «мусор» с понятными именами,
   файлы разложатся по папкам типов, для приложений создадутся
   ярлыки в категориях, установщики улетят в Корзину.

4. Если что-то пошло не так — «Отменить последнее»:
   перемещённые файлы вернутся на свои места.

ФОНОВЫЙ МОНИТОРИНГ
Включи тумблер «Мониторинг» — новые скриншоты будут
переименованы и убраны сразу после создания.

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
            self.collect_answers()
        if self.page == 3:
            self.cfg["onboarding_done"] = True
            utils.save_json(config.CONFIG_PATH, self.cfg)
            self.destroy()
            self.on_finish(scan_now=True)
            return
        self.show_page(self.page + 1)

    def collect_answers(self):
        f = self.cfg["folders"]
        f["musor"] = self.vars["musor"].get().strip() or "мусор"
        f["apps"] = self.vars["apps"].get().strip() or "Apps"
        f["files"] = self.vars["files"].get().strip() or "Файлы"
        for k in self.cfg["features"]:
            self.cfg["features"][k] = self.vars[f"feat_{k}"].get()
        self.cfg["enabled_types"] = [t for t in list(sorter.TYPE_MAP.keys()) + ["Другое"]
                                     if self.vars[f"type_{t}"].get()]

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
                "• установщики → в Корзину\n\n"
                "Ничего не удаляется навсегда и не меняется без твоего подтверждения.")).pack(padx=30)
            self.nav()
        elif n == 1:
            ctk.CTkLabel(self.frame, text="Как это работает", font=("", 24, "bold")).pack(pady=(30, 8))
            ctk.CTkLabel(self.frame, justify="left", font=("", 14), text=(
                "1. «Сканировать систему» — один проход по столу, загрузкам и приложениям.\n"
                "2. Тебе показывается список действий с галочками — сними лишние.\n"
                "3. «Применить выбранные» — выполняются только отмеченные.\n"
                "4. «Отменить последнее» — откат перемещений, если передумал(а).\n\n"
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
                             ("installers", "установщики в Корзину")):
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
    def __init__(self, cfg: dict):
        super().__init__()
        self.cfg = cfg
        self.actions: list[dict] = []
        self.history = utils.load_json(config.HISTORY_PATH, [])
        self.observer = None
        self.title("DesktopKeeper")
        self.geometry("760x620")

        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", padx=14, pady=(14, 6))
        self.btn_scan = ctk.CTkButton(top, text="Сканировать систему", command=self.scan)
        self.btn_scan.pack(side="left")
        ToolTip(self.btn_scan, "Один проход по рабочему столу, загрузкам и приложениям:\nпокажу список действий с галочками")
        self.btn_apply = ctk.CTkButton(top, text="Применить выбранные (0)",
                                       state="disabled", command=self.apply)
        self.btn_apply.pack(side="left", padx=8)
        ToolTip(self.btn_apply, "Выполняются ТОЛЬКО отмеченные галочками действия")
        self.btn_undo = ctk.CTkButton(top, text="Отменить последнее",
                                      fg_color="#7a3b3b", command=self.undo)
        self.btn_undo.pack(side="left")
        ToolTip(self.btn_undo, "Вернёт перемещённые файлы последней уборки на свои места")

        mid = ctk.CTkFrame(self, fg_color="transparent")
        mid.pack(fill="x", padx=14)
        self.mon = ctk.CTkSwitch(mid, text="Мониторинг скринов", command=self.toggle_watch)
        self.mon.pack(side="left")
        ToolTip(self.mon, "Новые скриншоты переименовываются и убираются сразу после создания")
        ctk.CTkButton(mid, text="Категории", width=100, fg_color="#3a3a3a",
                      command=self.edit_categories).pack(side="right", padx=4)
        ctk.CTkButton(mid, text="Справка", width=90, fg_color="#3a3a3a",
                      command=self.show_help).pack(side="right")

        self.status = ctk.CTkLabel(self, text="Нажми «Сканировать систему»", anchor="w")
        self.status.pack(fill="x", padx=16, pady=(6, 2))

        self.list = ctk.CTkScrollableFrame(self, label_text="Предлагаемые действия")
        self.list.pack(fill="both", expand=True, padx=14, pady=(4, 14))

    # ---------- скан и предпросмотр ----------
    def scan(self):
        self.status.configure(text="Сканирую…")
        self.update_idletasks()
        for w in self.list.winfo_children():
            w.destroy()
        self.actions = build_actions(self.cfg)
        if not self.actions:
            self.status.configure(text="Порядок: действий нет.")
            self.btn_apply.configure(state="disabled", text="Применить выбранные (0)")
            return
        for a in self.actions:
            a["var"] = ctk.BooleanVar(value=True)
            cb = ctk.CTkCheckBox(self.list, text=a["desc"], variable=a["var"],
                                 command=self.refresh_count)
            cb.pack(anchor="w", padx=10, pady=3)
        self.refresh_count()
        self.status.configure(text=f"Найдено действий: {len(self.actions)}. Сними галочки с лишнего и жми «Применить».")

    def refresh_count(self):
        n = sum(1 for a in self.actions if a["var"].get())
        self.btn_apply.configure(state="normal" if n else "disabled",
                                 text=f"Применить выбранные ({n})")

    # ---------- применение и откат ----------
    def apply(self):
        n = sum(1 for a in self.actions if a["var"].get())
        if not messagebox.askyesno("Подтверждение", f"Выполнить действий: {n}?"):
            return
        done = apply_actions(self.actions, self.history)
        self.actions = []
        for w in self.list.winfo_children():
            w.destroy()
        self.btn_apply.configure(state="disabled", text="Применить выбранные (0)")
        self.status.configure(text=f"Готово: выполнено {done}.")

    def undo(self):
        n = undo_last(self.history)
        messagebox.showinfo("Отмена", f"Возвращено файлов: {n}.\n(Корзина и ярлыки не откатываются.)")
        self.status.configure(text=f"Откат: возвращено {n} файлов.")

    # ---------- мониторинг ----------
    def toggle_watch(self):
        if self.mon.get():
            def on_shot(p: Path):
                shots.process(p, self.history, live=True)
                utils.save_json(config.HISTORY_PATH, self.history)
                self.after(0, lambda: self.status.configure(
                    text=f"[мониторинг] {p.name} → {self.cfg['folders']['musor']}"))
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
            cats.add_category(name)
            self.cfg["categories"].setdefault(name, [])
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
    cfg = load_cfg()
    apply_folder_names(cfg)
    app = Main(cfg)
    if scan_now:
        app.after(300, app.scan)
    app.mainloop()


if __name__ == "__main__":
    cfg = load_cfg()
    apply_folder_names(cfg)
    if not cfg["onboarding_done"]:
        Wizard(cfg, on_finish=lambda scan_now=False: start_main(scan_now)).mainloop()
    else:
        start_main()