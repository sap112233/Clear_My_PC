"""Saved collections of applications and websites for starting a work session."""
from __future__ import annotations

import os
import subprocess
import webbrowser
from pathlib import Path
from urllib.parse import urlsplit

import platform_tools as pt


def validate_website(url: str) -> str:
    if not isinstance(url, str):
        raise ValueError("Адрес сайта должен быть строкой.")
    url = url.strip()
    try:
        parsed = urlsplit(url)
        hostname = parsed.hostname
        parsed.port
    except ValueError as exc:
        raise ValueError(f"Некорректный адрес сайта: {url}") from exc
    if (
        any(character.isspace() or ord(character) < 32 for character in url)
        or parsed.scheme.lower() not in {"http", "https"}
        or not parsed.netloc
        or not hostname
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise ValueError("Укажи полный адрес сайта, начинающийся с http:// или https://.")
    return url


def validate_profiles(profiles: object) -> list[dict]:
    if not isinstance(profiles, list):
        raise ValueError("Рабочие профили должны быть списком.")
    result = []
    names = set()
    for profile in profiles:
        if not isinstance(profile, dict):
            raise ValueError("Каждый рабочий профиль должен быть объектом.")
        name = profile.get("name")
        applications = profile.get("apps", [])
        websites = profile.get("websites", [])
        if not isinstance(name, str) or not name.strip() or len(name.strip()) > 80:
            raise ValueError("Название профиля должно содержать от 1 до 80 символов.")
        name = name.strip()
        if name.casefold() in names:
            raise ValueError(f"Профиль «{name}» уже существует.")
        names.add(name.casefold())
        if not isinstance(applications, list) or not isinstance(websites, list):
            raise ValueError(f"Приложения и сайты профиля «{name}» должны быть списками.")

        checked_apps = []
        seen_apps = set()
        for application in applications:
            if not isinstance(application, dict):
                raise ValueError(f"Приложение профиля «{name}» имеет неверный формат.")
            app_name, app_path = application.get("name"), application.get("path")
            if (
                not isinstance(app_name, str)
                or not app_name.strip()
                or not isinstance(app_path, str)
                or not Path(app_path).is_absolute()
            ):
                raise ValueError(f"Приложение профиля «{name}» имеет неверный путь или имя.")
            identity = app_path.casefold()
            if identity not in seen_apps:
                checked_apps.append({"name": app_name.strip(), "path": app_path})
                seen_apps.add(identity)

        checked_websites = []
        seen_urls = set()
        for website in websites:
            if not isinstance(website, dict):
                raise ValueError(f"Сайт профиля «{name}» имеет неверный формат.")
            website_name, url = website.get("name"), website.get("url")
            if not isinstance(website_name, str) or not website_name.strip():
                raise ValueError(f"Сайт профиля «{name}» должен иметь название.")
            url = validate_website(url)
            if url not in seen_urls:
                checked_websites.append(
                    {"name": website_name.strip(), "url": url}
                )
                seen_urls.add(url)

        result.append(
            {"name": name, "apps": checked_apps, "websites": checked_websites}
        )
    return result


def _installed_application(path: Path) -> Path:
    if path.is_symlink():
        raise ValueError(f"Нельзя запускать приложение через символическую ссылку: {path}")
    try:
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise FileNotFoundError(f"Приложение не найдено: {path}") from exc
    roots = [root.resolve() for root in pt.app_dirs() if not root.is_symlink()]
    if not any(
        (relative := _relative_to(resolved, root)) is not None and relative.parts
        for root in roots
    ):
        raise ValueError(f"Приложение находится вне системных папок приложений: {path}")
    supported = (
        (pt.IS_MAC and resolved.suffix.lower() == ".app" and resolved.is_dir())
        or (pt.IS_WIN and resolved.suffix.lower() == ".lnk" and resolved.is_file())
        or (
            pt.IS_LINUX
            and resolved.suffix.lower() == ".desktop"
            and resolved.is_file()
        )
    )
    if not supported:
        raise ValueError(f"Неподдерживаемый тип приложения: {path}")
    return resolved


def _relative_to(path: Path, root: Path) -> Path | None:
    try:
        return path.relative_to(root)
    except ValueError:
        return None


def launch_application(path: str) -> None:
    app_path = _installed_application(Path(path))
    if pt.IS_MAC:
        subprocess.Popen(["open", "-a", str(app_path)])
    elif pt.IS_WIN:
        os.startfile(str(app_path))
    else:
        subprocess.Popen(["gio", "launch", str(app_path)])


def launch_profile(profile: dict) -> list[str]:
    """Open every selected item and return per-item errors without hiding failures."""
    checked = validate_profiles([profile])[0]
    errors = []
    for application in checked["apps"]:
        try:
            launch_application(application["path"])
        except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
            errors.append(f"{application['name']}: {exc}")
    for website in checked["websites"]:
        try:
            if not webbrowser.open(website["url"], new=2):
                raise RuntimeError("Не удалось открыть ссылку в браузере.")
        except (OSError, ValueError, RuntimeError, webbrowser.Error) as exc:
            errors.append(f"{website['name']}: {exc}")
    return errors
