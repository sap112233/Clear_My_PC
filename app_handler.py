"""Обработка приложений: детект, категоризация, алиасы, удаление установщиков."""
from __future__ import annotations

import platform_tools as pt
import json
import subprocess
from pathlib import Path

import config
from utils import load_json, save_json, sanitize, logged_move


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
                    save_json(config.CONFIG_PATH, {"categories": categories})
                    return new_cat
        print("Неверный выбор, попробуй снова.")


def create_alias(app_path: Path, category: str) -> Path:
    target_folder = config.APPS_ROOT / category
    target_folder.mkdir(parents=True, exist_ok=True)
    alias_path = target_folder / app_path.stem
    if alias_path.exists() or alias_path.is_symlink() or alias_path.with_suffix(".lnk").exists():
        print(f"  Ярлык уже существует: {alias_path}")
        return alias_path
    try:
        real = pt.create_shortcut(app_path, alias_path)
        print(f"  Создан ярлык: {real}")
        return real
    except Exception as e:
        print(f"  Ошибка создания ярлыка: {e}")
        return None


def move_to_trash(path: Path, history: list) -> None:
    try:
        if pt.send_to_trash(path):
            history.append({
                "ts": __import__("datetime").datetime.now().isoformat(),
                "action": "trash",
                "src": str(path),
            })
            print(f"  Удалено в Корзину: {path.name}")
    except Exception as e:
        print(f"  Ошибка удаления: {e}")


def scan_applications() -> list[Path]:
    """Сканируем /Applications и ~/Applications на .app"""
    apps = []
    for folder in config.APP_DIRS:
        if folder.is_dir():
            apps += [f for f in folder.iterdir() if f.suffix == pt.APP_EXT]
    return apps


def scan_downloads() -> list[Path]:
    """Сканируем ~/Downloads на установщики."""
    installers = []
    if config.DOWNLOADS.is_dir():
        for f in config.DOWNLOADS.iterdir():
            if f.suffix.lower() in pt.INSTALLER_EXTS:
                installers.append(f)
    return installers


def process_applications(history: list, dry_run: bool = False) -> None:
    """Основная логика: сканируем, категоризируем, создаём алиасы."""
    # Загружаем состояние и категории
    state = load_json(config.STATE_PATH, {"processed": []})
    config_data = load_json(config.CONFIG_PATH, {"categories": {}})
    categories = config_data.get("categories", {})
    
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
        
        new_apps.append((app, app_name, bundle_id))
    
    if not new_apps:
        print("Нет новых приложений для обработки.")
        return
    
    print(f"\nНовых приложений: {len(new_apps)}")
    
    if dry_run:
        print("\nПредпросмотр (dry run):")
        for app, app_name, bundle_id in new_apps:
            category = find_category(app_name, bundle_id, categories)
            if not category:
                category = "Утилиты"  # дефолт для предпросмотра
            print(f"  {app_name} → Apps/{category}")
        return
    
    # Обрабатываем каждое приложение
    for app, app_name, bundle_id in new_apps:
        print(f"\nОбработка: {app_name}")
        
        # Ищем категорию
        category = find_category(app_name, bundle_id, categories)
        if not category:
            category = ask_category(app_name, categories)
        
        # Создаём алиас
        alias_path = create_alias(app, category)
        
        # Добавляем в обработанные
        state["processed"].append(app_name)
        if bundle_id:
            state["processed"].append(bundle_id)
        
        # Логируем
        history.append({
            "ts": __import__("datetime").datetime.now().isoformat(),
            "action": "alias",
            "app": app_name,
            "category": category,
            "alias": str(alias_path) if alias_path else None,
        })
    
    # Сохраняем состояние
    save_json(config.STATE_PATH, state)
    save_json(config.CONFIG_PATH, {"categories": categories})
    
    print(f"\nГотово. Обработано: {len(new_apps)} приложений.")


def process_installers(history: list) -> None:
    """Удаляем установщики, если приложение уже установлено."""
    installers = scan_downloads()
    if not installers:
        return
    
    print(f"\nНайдено установщиков: {len(installers)}")
    
    apps = scan_applications()
    app_names = {get_app_name(a).lower() for a in apps}
    
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
            print(f"  Приложение найдено, удаляем установщик: {installer.name}")
            move_to_trash(installer, history)
        else:
            print(f"  Приложение не найдено, пропускаем: {installer.name}")