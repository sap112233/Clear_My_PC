"""Path and classification rules for safe, configurable desktop organization."""
from __future__ import annotations

import re
from pathlib import Path

import utils

LOCATION_KEYS = ("screenshots", "files", "apps")
FILE_TYPE_MIGRATION_VERSION = 1
DEFAULT_FOLDER_NAMES = {
    "screenshots": "мусор",
    "files": "Файлы",
    "apps": "Apps",
}


def migrate_enabled_file_types(settings: dict) -> None:
    version = settings.get("file_type_migrations", 0)
    if not isinstance(version, int) or isinstance(version, bool) or version < 0:
        raise ValueError("Версия настроек типов файлов задана неверно.")
    if version >= FILE_TYPE_MIGRATION_VERSION:
        return

    enabled_types = settings.get("enabled_types", [])
    if not isinstance(enabled_types, list):
        raise ValueError("Список типов файлов должен быть массивом.")
    if (
        "enabled_types" in settings
        and "Изображения" in enabled_types
        and "Графические проекты" not in enabled_types
    ):
        enabled_types.append("Графические проекты")
    settings["file_type_migrations"] = FILE_TYPE_MIGRATION_VERSION


def validate_custom_root(value: str, home: Path) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Путь пользовательской папки не может быть пустым.")
    path = Path(value).expanduser()
    if not path.is_absolute():
        raise ValueError(f"Путь папки должен быть абсолютным: {value}")
    resolved = path.resolve()
    home_resolved = home.resolve()
    if resolved == home_resolved or home_resolved not in resolved.parents:
        raise ValueError(
            f"Для безопасности выбери папку внутри домашней папки пользователя: {path}"
        )
    private_data = (home_resolved / ".desktop-keeper").resolve()
    if resolved == private_data or private_data in resolved.parents:
        raise ValueError("Нельзя использовать папку данных DesktopKeeper как место сортировки.")
    return resolved


def default_locations(desktop: Path, folder_names: dict) -> dict[str, Path]:
    names = {
        "screenshots": folder_names.get("musor", DEFAULT_FOLDER_NAMES["screenshots"]),
        "files": folder_names.get("files", DEFAULT_FOLDER_NAMES["files"]),
        "apps": folder_names.get("apps", DEFAULT_FOLDER_NAMES["apps"]),
    }
    return {
        key: utils.safe_child_path(desktop, names[key])
        for key in LOCATION_KEYS
    }


def resolve_locations(
    cfg: dict,
    desktop: Path,
    home: Path,
) -> dict[str, Path]:
    mode = cfg.get("layout_mode", "automatic")
    if mode not in {"automatic", "custom"}:
        raise ValueError("Режим папок должен быть automatic или custom.")

    if mode == "automatic":
        paths = default_locations(desktop, cfg.get("folders", {}))
    else:
        configured = cfg.get("locations")
        if not isinstance(configured, dict):
            raise ValueError("Для пользовательского режима укажи пути папок.")
        paths = {}
        for key in LOCATION_KEYS:
            value = configured.get(key)
            paths[key] = validate_custom_root(value, home)

    normalized = [str(paths[key]).casefold() for key in LOCATION_KEYS]
    if len(set(normalized)) != len(normalized):
        raise ValueError("Папки скриншотов, файлов и приложений должны различаться.")
    return paths


def configure_screenshot_folder(
    cfg: dict,
    choice: str,
    selected_folder: str | None,
    desktop: Path,
    home: Path,
) -> None:
    if choice == "leave":
        cfg["features"]["screenshots"] = False
        return
    if choice == "desktop":
        return
    if choice != "existing":
        raise ValueError("Выбери папку для скриншотов.")
    if not selected_folder:
        raise ValueError("Выбери существующую папку для скриншотов.")

    screenshot_root = validate_custom_root(selected_folder, home)
    if not screenshot_root.is_dir():
        raise ValueError(f"Папка для скриншотов не существует: {screenshot_root}")

    if cfg.get("layout_mode", "automatic") == "automatic":
        paths = default_locations(desktop, cfg.get("folders", {}))
    else:
        paths = resolve_locations(cfg, desktop, home)
    paths["screenshots"] = screenshot_root
    cfg["layout_mode"] = "custom"
    cfg["locations"] = {key: str(path) for key, path in paths.items()}
    resolve_locations(cfg, desktop, home)


def validate_excluded_folders(values: object) -> list[Path]:
    if not isinstance(values, list):
        raise ValueError("Список защищённых папок должен быть массивом.")

    folders = []
    seen = set()
    for value in values:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("Путь защищённой папки не может быть пустым.")
        path = Path(value).expanduser()
        if not path.is_absolute():
            raise ValueError(f"Путь защищённой папки должен быть абсолютным: {value}")
        if path.is_symlink():
            raise ValueError(f"Защищённую папку нельзя задавать через ссылку: {path}")
        resolved = path.resolve()
        if resolved == Path(resolved.anchor):
            raise ValueError("Нельзя защищать корень диска вместо конкретной папки.")
        key = str(resolved).casefold()
        if key not in seen:
            folders.append(resolved)
            seen.add(key)
    return folders


def is_excluded_path(path: Path, excluded_folders: list[Path]) -> bool:
    resolved = path.resolve()
    return any(
        resolved == excluded.resolve() or excluded.resolve() in resolved.parents
        for excluded in excluded_folders
    )


def validate_custom_file_types(
    definitions: object,
    built_in_types: dict[str, set[str]],
) -> dict[str, list[str]]:
    if not isinstance(definitions, dict):
        raise ValueError("Пользовательские типы файлов должны быть JSON-объектом.")

    normalized: dict[str, list[str]] = {}
    seen_extensions: set[str] = set()
    built_in_names = {name.casefold() for name in built_in_types} | {"другое"}
    seen_names: set[str] = set()
    for raw_name, raw_extensions in definitions.items():
        if not isinstance(raw_name, str) or not isinstance(raw_extensions, list):
            raise ValueError("Имя пользовательского типа и расширения заданы неверно.")
        name = utils.sanitize(raw_name)
        if name != raw_name or name.casefold() in built_in_names:
            raise ValueError(f"Недопустимое или уже занятое имя типа: {raw_name!r}")
        if name.casefold() in seen_names:
            raise ValueError(f"Имя типа {name!r} уже используется.")
        seen_names.add(name.casefold())
        if not raw_extensions:
            raise ValueError(f"Для типа «{name}» укажи хотя бы одно расширение.")
        extensions = []
        for value in raw_extensions:
            if not isinstance(value, str):
                raise ValueError(f"Расширение файла должно быть строкой: {value!r}")
            extension = value.strip().lower()
            if not extension.startswith("."):
                extension = f".{extension}"
            if not re.fullmatch(r"\.[a-z0-9][a-z0-9_+-]{0,19}", extension):
                raise ValueError(f"Недопустимое расширение файла: {value!r}")
            if extension in seen_extensions:
                raise ValueError(f"Расширение {extension} назначено нескольким типам.")
            if any(extension in exts for exts in built_in_types.values()):
                raise ValueError(
                    f"Расширение {extension} уже используется встроенным типом."
                )
            seen_extensions.add(extension)
            extensions.append(extension)
        normalized[name] = extensions
    return normalized


def file_category_for(
    path: Path,
    built_in_types: dict[str, set[str]],
    custom_types: dict[str, list[str]],
) -> str:
    extension = path.suffix.lower()
    for name, extensions in custom_types.items():
        if extension in extensions:
            return name
    for name, extensions in built_in_types.items():
        if extension in extensions:
            return name
    return "Другое"


def category_folder_name(category: str) -> str:
    if not isinstance(category, str) or not category.strip():
        raise ValueError("Название категории не может быть пустым.")
    return utils.sanitize(category)


def app_destination(
    root: Path,
    category: str,
    app_name: str,
    is_mac: bool,
    is_linux: bool = False,
) -> Path:
    destination = utils.safe_child_path(
        root, category_folder_name(category), utils.sanitize(app_name)
    )
    if not is_mac:
        extension = ".desktop" if is_linux else ".lnk"
        destination = destination.with_name(f"{destination.name}{extension}")
    return destination


def app_shortcut_destination(
    folder: Path,
    app_name: str,
    is_mac: bool,
    is_linux: bool = False,
) -> Path:
    destination = utils.safe_child_path(folder, utils.sanitize(app_name))
    if not is_mac:
        extension = ".desktop" if is_linux else ".lnk"
        destination = destination.with_name(f"{destination.name}{extension}")
    return destination


def active_aliases(history: list[dict]) -> dict[str, dict]:
    aliases = {}
    for entry in history:
        action = entry.get("action")
        if action == "alias":
            app_source, alias_path = entry.get("src"), entry.get("dst") or entry.get("alias")
            if not isinstance(app_source, str):
                continue
            key = str(Path(app_source).resolve())
            if entry.get("undone"):
                aliases.pop(key, None)
            elif isinstance(alias_path, str):
                aliases[key] = {
                    "path": Path(alias_path),
                    "app": entry.get("app"),
                    "bundle_id": entry.get("bundle_id"),
                    "category": entry.get("category"),
                }
        elif action == "alias_move":
            app_source, old_path, new_path = (
                entry.get("app_src"),
                entry.get("src"),
                entry.get("dst"),
            )
            if not all(isinstance(value, str) for value in (app_source, old_path, new_path)):
                continue
            key = str(Path(app_source).resolve())
            aliases[key] = {
                "path": Path(old_path if entry.get("undone") else new_path),
                "app": entry.get("app"),
                "bundle_id": entry.get("bundle_id"),
                "category": entry.get("category"),
            }
    return aliases
