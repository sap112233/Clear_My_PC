"""DesktopKeeper — входная точка.
  python3 main.py                     # скриншоты: скан + предпросмотр + применение
  python3 main.py --watch             # фоновый мониторинг скринов
  python3 main.py --set-capture       # разово: системные скрины сразу в 'мусор'
  python3 main.py --scan-apps         # предпросмотр раскладки приложений
  python3 main.py --process-apps      # создать алиасы приложений
  python3 main.py --clean-installers  # установщики в Корзину
  python3 main.py --sort-files        # сортировка файлов стола по типам
  python3 main.py --add-category ИМЯ  # создать новую категорию внутри Apps
"""
import argparse
import time
from pathlib import Path

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

import app_handler as apps
import categories
import config
import file_sorter as sorter
import screenshot_handler as shots
import utils


class ShotWatcher(FileSystemEventHandler):
    def __init__(self, history: list):
        self.history = history

    def on_created(self, event):
        p = Path(event.src_path)
        if not shots.is_screenshot(p):
            return
        if not utils.wait_stable(p):
            return
        dst = shots.process(p, self.history, live=True)
        utils.save_json(config.HISTORY_PATH, self.history)
        print(f"[shot] {p.name}  →  {dst.name}")


def watch(history: list) -> None:
    obs = Observer()
    for folder in (config.DESKTOP, config.MUSOR):
        folder.mkdir(parents=True, exist_ok=True)
        obs.schedule(ShotWatcher(history), str(folder), recursive=False)
    obs.start()
    print("Мониторинг включён. Ctrl-C — стоп.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        obs.stop()
    obs.join()
    utils.save_json(config.HISTORY_PATH, history)


def clean_screenshots(history: list) -> None:
    found = shots.collect()
    if not found:
        print("Рабочий стол чист: скриншотов не найдено.")
        return
    print(f"\nНайдено скриншотов: {len(found)}. План:")
    for f in found:
        print(f"  {f.parent.name}/{f.name}  →  мусор/{shots.build_name(f, '', '')}")
    if input("\nПрименить? [y/N] ").strip().lower() != "y":
        print("Отменено.")
        return
    for f in found:
        shots.process(f, history)
    utils.save_json(config.HISTORY_PATH, history)
    print("Готово.")


def main() -> None:
    ap = argparse.ArgumentParser(description="DesktopKeeper")
    ap.add_argument("--watch", action="store_true")
    ap.add_argument("--set-capture", action="store_true")
    ap.add_argument("--scan-apps", action="store_true")
    ap.add_argument("--process-apps", action="store_true")
    ap.add_argument("--clean-installers", action="store_true")
    ap.add_argument("--sort-files", action="store_true")
    ap.add_argument("--add-category", metavar="NAME")
    args = ap.parse_args()

    history = utils.load_json(config.HISTORY_PATH, [])

    if args.set_capture:
        shots.set_system_capture_location()
    elif args.watch:
        watch(history)
    elif args.scan_apps:
        apps.process_applications(history, dry_run=True)
    elif args.process_apps:
        apps.process_applications(history, dry_run=False)
        utils.save_json(config.HISTORY_PATH, history)
    elif args.clean_installers:
        apps.process_installers(history)
        utils.save_json(config.HISTORY_PATH, history)
    elif args.sort_files:
        sorter.run(history)
    elif args.add_category:
        categories.add_category(args.add_category)
    else:
        clean_screenshots(history)


if __name__ == "__main__":
    main()