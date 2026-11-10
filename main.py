"""DesktopKeeper — входная точка.
  python3 main.py                     # скриншоты: скан + предпросмотр + применение
  python3 main.py --watch             # фоновый мониторинг скринов
  python3 main.py --set-capture       # разово: системные скрины сразу в 'мусор'
  python3 main.py --scan-apps         # предпросмотр раскладки приложений
  python3 main.py --process-apps      # создать алиасы приложений
  python3 main.py --clean-installers  # предпросмотр и перенос установщиков в архив
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
import organization
import screenshot_handler as shots
import utils


def load_user_settings() -> dict:
    settings = utils.load_json(config.CONFIG_PATH, {})
    if not isinstance(settings, dict):
        raise ValueError("Файл настроек должен содержать JSON-объект.")
    settings.setdefault("folders", {"musor": "мусор", "apps": "Apps", "files": "Файлы"})
    if not isinstance(settings["folders"], dict) or any(
        not isinstance(value, str) for value in settings["folders"].values()
    ):
        raise ValueError("Имена рабочих папок должны быть строками.")
    settings.setdefault("layout_mode", "automatic")
    settings.setdefault("locations", {})
    settings.setdefault("screenshot_retention_minutes", 0)
    settings["screenshot_retention_minutes"] = shots.validate_retention_minutes(
        settings["screenshot_retention_minutes"]
    )
    settings["excluded_folders"] = [
        str(path)
        for path in organization.validate_excluded_folders(
            settings.setdefault("excluded_folders", [])
        )
    ]
    config.EXCLUDED_FOLDERS = [
        Path(path) for path in settings["excluded_folders"]
    ]
    settings.setdefault("custom_file_types", {})
    settings["custom_file_types"] = organization.validate_custom_file_types(
        settings["custom_file_types"], sorter.TYPE_MAP
    )
    settings.setdefault(
        "enabled_types",
        list(sorter.TYPE_MAP)
        + list(settings["custom_file_types"])
        + ["Другое"],
    )
    if not isinstance(settings["enabled_types"], list) or any(
        not isinstance(item, str) for item in settings["enabled_types"]
    ):
        raise ValueError("Список типов файлов должен быть массивом строк.")
    organization.migrate_enabled_file_types(settings)
    available_types = (
        set(sorter.TYPE_MAP) | set(settings["custom_file_types"]) | {"Другое"}
    )
    if any(item not in available_types for item in settings["enabled_types"]):
        raise ValueError("Включён неизвестный тип файлов.")

    locations = organization.resolve_locations(
        settings, config.DESKTOP, config.HOME
    )
    config.MUSOR = locations["screenshots"]
    config.FILES_ROOT = locations["files"]
    config.APPS_ROOT = locations["apps"]
    return settings


class ShotWatcher(FileSystemEventHandler):
    def __init__(self, history: list):
        self.history = history

    def on_created(self, event):
        p = Path(event.src_path)
        if organization.is_excluded_path(p, config.EXCLUDED_FOLDERS):
            return
        if not shots.is_screenshot(p):
            return
        if not utils.wait_stable(p):
            return
        destination = utils.unique_dst(
            config.MUSOR / shots.build_name(p, "", "")
        )
        if organization.is_excluded_path(destination, config.EXCLUDED_FOLDERS):
            print(f"Пропускаю скриншот: папка назначения защищена: {destination.parent}")
            return
        print(f"\nПредпросмотр нового скриншота:\n  {p} → {destination}")
        if input("Разрешить перемещение? [y/N] ").strip().lower() != "y":
            print("Оставляю файл на месте.")
            return
        if organization.is_excluded_path(p, config.EXCLUDED_FOLDERS) or organization.is_excluded_path(
            destination, config.EXCLUDED_FOLDERS
        ):
            raise ValueError("Скриншот или его назначение попадает в защищённую папку.")
        dst = utils.logged_move(p, destination, self.history, allow_unique=False)
        utils.save_json(config.HISTORY_PATH, self.history)
        print(f"[shot] {p.name}  →  {dst.name}")


def watch(history: list) -> None:
    obs = Observer()
    folders = dict.fromkeys(
        folder.resolve()
        for folder in (config.DESKTOP, config.MUSOR)
        if folder.is_dir()
        and not organization.is_excluded_path(folder, config.EXCLUDED_FOLDERS)
    )
    if not folders:
        print("Нет доступных существующих папок для мониторинга. Папки не создавались.")
        return
    for folder in folders:
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
    planned = []
    reserved = set()
    for source in found:
        destination = utils.unique_dst(
            config.MUSOR / shots.build_name(source, "", ""), reserved
        )
        planned.append((source, destination))
    print(f"\nНайдено скриншотов: {len(planned)}. План:")
    for source, destination in planned:
        print(f"  {source}  →  {destination}")
    if input("\nПрименить? [y/N] ").strip().lower() != "y":
        print("Отменено.")
        return
    for source, destination in planned:
        utils.logged_move(source, destination, history, allow_unique=False)
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

    settings = load_user_settings()
    history = utils.load_json(config.HISTORY_PATH, [])
    if not isinstance(history, list) or any(
        not isinstance(entry, dict) for entry in history
    ):
        raise ValueError("История действий должна быть списком JSON-объектов.")

    if args.set_capture:
        print(f"Место сохранения скриншотов будет изменено на: {config.MUSOR}")
        if input("Применить это системное изменение? [y/N] ").strip().lower() == "y":
            shots.set_system_capture_location()
        else:
            print("Отменено.")
    elif args.watch:
        watch(history)
    elif args.scan_apps:
        apps.process_applications(history, dry_run=True)
    elif args.process_apps:
        if apps.process_applications(history, dry_run=False):
            utils.save_json(config.HISTORY_PATH, history)
    elif args.clean_installers:
        if apps.process_installers(history):
            utils.save_json(config.HISTORY_PATH, history)
    elif args.sort_files:
        sorter.run(
            history,
            settings["custom_file_types"],
            settings["enabled_types"],
        )
    elif args.add_category:
        categories.add_category(args.add_category)
    else:
        clean_screenshots(history)


if __name__ == "__main__":
    main()