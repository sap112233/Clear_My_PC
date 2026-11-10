"""Обработка приложений: детект, категоризация, алиасы, удаление установщиков."""
from __future__ import annotations

import platform_tools as pt
import subprocess
import uuid
from datetime import datetime
from pathlib import Path

import config
from utils import load_json, save_json, safe_child_path, logged_move, unique_dst


def get_bundle_id(app_path: Path) -> str:

    """Получаем Bundle ID приложения (уникальный идентификатор)."""
    
    plist = app_path / "Contents" / "Info.plist"
    if not pt.IS_MAC:
        return ""
    if plist.is_file():
        try:
            r = subprocess.run(
                ["plutil", "-extract", "CFBundleIdentifier", "raw", "-o", "-", str(plist)],
                capture_output=True, text=True, timeout=2
            )
            if r.returncode == 0:
                return r.stdout.strip()
        except Exception:
            pass
    return ""


def get_app_name(app_path: Path) -> str:
    """Получаем читаемое имя приложения."""
    return app_path.stem.replace(".app", "")


def find_category(app_name: str, bundle_id: str, categories: dict) -> str | None:
    """Ищем категорию по имени или Bundle ID."""
    app_name_lower = app_name.lower()
    bundle_id_lower = bundle_id.lower()
    
    for category, apps in categories.items():
        for app in apps:
            if app.lower() in app_name_lower or app.lower() in bundle_id_lower:
                return category
    return None


def ask_category(app_name: str, categories: dict) -> str:
    """Спрашиваем пользователя о категории (CLI)."""
    print(f"\nПриложение '{app_name}' не найдено в словаре.")
    print("Доступные категории:")
    for i, cat in enumerate(categories.keys(), 1):
        print(f"  {i}. {cat}")
    print(f"  {len(categories) + 1}. Создать новую категорию")
    
    while True:
        choice = input("Выбери номер категории: ").strip()
        if choice.isdigit():
            choice = int(choice)
            if 1 <= choice <= len(categories):
                return list(categories.keys())[choice - 1]
            elif choice == len(categories) + 1:
                new_cat = input("Название новой категории: ").strip()
                if new_cat:
                    categories[new_cat] = []
                    return new_cat
        print("Неверный выбор, попробуй снова.")


def create_alias(app_path: Path, category: str) -> Path | None:
    target_folder = safe_child_path(config.APPS_ROOT, category)
    target_folder.mkdir(parents=True, exist_ok=True)
    alias_path = safe_child_path(target_folder, app_path.stem)
    if alias_path.exists() or alias_path.is_symlink() or alias_path.with_suffix(".lnk").exists():
        print(f"  Пропускаю, ярлык уже существует: {alias_path}")
        return None
    try:
        real = pt.create_shortcut(app_path, alias_path)
        print(f"  Создан ярлык: {real}")
        return real
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as e:
        print(f"  Ошибка создания ярлыка: {e}")
        return None


def quarantine_installer(path: Path, history: list, destination: Path | None = None) -> bool:
    try:
        dst = destination or unique_dst(config.QUARANTINE_DIR / path.name)
        utils_path = logged_move(path, dst, history, allow_unique=False)
        print(f"  Перемещено в защищённое хранилище: {utils_path}")
        return True
    except OSError as e:
        print(f"  Ошибка перемещения: {e}")
        return False


def scan_applications() -> list[Path]:
    """Сканируем /Applications и ~/Applications на .app"""
    apps = []
    for folder in config.APP_DIRS:
        if folder.is_dir():
            apps += [
                f for f in folder.iterdir()
                if f.suffix == pt.APP_EXT and not f.is_symlink()
            ]
    return apps


def scan_downloads() -> list[Path]:
    """Сканируем ~/Downloads на установщики."""
    installers = []
    if config.DOWNLOADS.is_dir():
        for f in config.DOWNLOADS.iterdir():
            if f.suffix.lower() in pt.INSTALLER_EXTS and not f.is_symlink():
                installers.append(f)
    return installers


def process_applications(history: list, dry_run: bool = False) -> bool:
    """Основная логика: сканируем, категоризируем, создаём алиасы."""
    # Загружаем состояние и категории
    state = load_json(config.STATE_PATH, {"processed": []})
    if (
        not isinstance(state, dict)
        or not isinstance(state.get("processed", []), list)
        or any(not isinstance(item, str) for item in state.get("processed", []))
    ):
        raise ValueError("Файл состояния приложения имеет неверный формат.")
    config_data = load_json(config.CONFIG_PATH, {"categories": {}})
    if not isinstance(config_data, dict):
        raise ValueError("Файл настроек должен содержать JSON-объект.")
    categories = config_data.get("categories", {})
    if not isinstance(categories, dict) or any(
        not isinstance(category, str)
        or not isinstance(names, list)
        or any(not isinstance(name, str) for name in names)
        for category, names in categories.items()
    ):
        raise ValueError("Настройка категорий должна быть JSON-объектом.")
    
    # Сканируем приложения
    apps = scan_applications()
    print(f"\nНайдено приложений: {len(apps)}")
    
    # Первичный разбор: показываем все новые приложения
    new_apps = []
    for app in apps:
        bundle_id = get_bundle_id(app)
        app_name = get_app_name(app)
        
        # Проверяем, обработано ли уже
        if app_name in state["processed"] or bundle_id in state["processed"]:
            continue
        
        category = find_category(app_name, bundle_id, categories)
        if not category and not dry_run:
            category = ask_category(app_name, categories)
        category = category or "Утилиты"
        safe_child_path(config.APPS_ROOT, category, app.stem)
        new_apps.append((app, app_name, bundle_id, category))
    
    if not new_apps:
        print("Нет новых приложений для обработки.")
        return False
    
    print(f"\nНовых приложений: {len(new_apps)}")
    
    if dry_run:
        print("\nПредпросмотр (dry run):")
        for app, app_name, bundle_id, category in new_apps:
            destination = safe_child_path(config.APPS_ROOT, category, app.stem)
            if not pt.IS_MAC:
                destination = destination.with_suffix(".lnk")
            print(f"  Создать ярлык: {app} → {destination}")
        return False

    print("\nПредпросмотр действий:")
    for app, app_name, bundle_id, category in new_apps:
        destination = safe_child_path(config.APPS_ROOT, category, app.stem)
        if not pt.IS_MAC:
            destination = destination.with_suffix(".lnk")
        print(f"  Создать ярлык: {app} → {destination}")
    if input("\nСоздать эти ярлыки? [y/N] ").strip().lower() != "y":
        print("Отменено.")
        return False

    # Обрабатываем каждое приложение
    batch = uuid.uuid4().hex
    created = 0
    for app, app_name, bundle_id, category in new_apps:
        print(f"\nОбработка: {app_name}")

        # Создаём алиас
        alias_path = create_alias(app, category)
        if alias_path is None:
            continue
        created += 1
        
        # Добавляем в обработанные
        state["processed"].append(app_name)
        if bundle_id:
            state["processed"].append(bundle_id)
        
        # Логируем
        history.append({
            "ts": datetime.now().isoformat(),
            "action": "alias",
            "src": str(app),
            "dst": str(alias_path),
            "app": app_name,
            "bundle_id": bundle_id,
            "category": category,
            "batch": batch,
        })
        save_json(config.HISTORY_PATH, history)
    
    # Сохраняем состояние
    save_json(config.STATE_PATH, state)
    config_data["categories"] = categories
    save_json(config.CONFIG_PATH, config_data)

    print(f"\nГотово. Создано ярлыков: {created}.")
    return created > 0


def process_installers(history: list) -> bool:
    """Переносим установщики уже установленных приложений в защищённый архив."""
    installers = scan_downloads()
    if not installers:
        return False
    
    print(f"\nНайдено установщиков: {len(installers)}")
    
    apps = scan_applications()
    app_names = {get_app_name(a).lower() for a in apps}
    
    matches = []
    for installer in installers:
        # Пытаемся угадать имя приложения по имени установщика
        installer_name = installer.stem.lower()
        
        # Проверяем, есть ли приложение с похожим именем
        installed = False
        for app_name in app_names:
            if installer_name in app_name or app_name in installer_name:
                installed = True
                break
        
        if installed:
            matches.append(installer)
        else:
            print(f"  Приложение не найдено, пропускаем: {installer.name}")

    if not matches:
        print("Установщиков для перемещения нет.")
        return False

    planned = [
        (installer, unique_dst(config.QUARANTINE_DIR / installer.name))
        for installer in matches
    ]
    print("\nПредпросмотр действий:")
    for installer, destination in planned:
        print(f"  {installer} → {destination}")
    if input("\nПереместить установщики в защищённое хранилище? [y/N] ").strip().lower() != "y":
        print("Отменено.")
        return False

    moved = 0
    for installer, destination in planned:
        if quarantine_installer(installer, history, destination):
            moved += 1
    return moved > 0