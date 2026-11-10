"""Автозапуск при входе в систему: macOS (LaunchAgent) и Windows (Run key)."""
from __future__ import annotations

import subprocess
import sys
import plistlib
import tempfile
from pathlib import Path

import platform_tools as pt
from utils import safe_child_path

LABEL = "com.desktopkeeper"
PLIST = safe_child_path(Path.home(), "Library", "LaunchAgents", f"{LABEL}.plist")
LINUX_AUTOSTART = safe_child_path(
    Path.home(), ".config", "autostart", "desktopkeeper.desktop"
)


def _is_our_linux_entry() -> bool:
    if LINUX_AUTOSTART.is_symlink() or not LINUX_AUTOSTART.is_file():
        return False
    try:
        content = LINUX_AUTOSTART.read_text(encoding="utf-8")
    except OSError:
        return False
    return (
        "[Desktop Entry]" in content
        and "Name=DesktopKeeper" in content
        and "X-DesktopKeeper-Autostart=true" in content
    )


def _desktop_exec_argument(value: str) -> str:
    escaped = (
        value.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("%", "%%")
    )
    return f'"{escaped}"'


def _linux_autostart_content(command: list[str]) -> str:
    exec_line = " ".join(_desktop_exec_argument(argument) for argument in command)
    return (
        "[Desktop Entry]\n"
        "Type=Application\n"
        "Name=DesktopKeeper\n"
        f"Exec={exec_line}\n"
        "Terminal=false\n"
        "X-DesktopKeeper-Autostart=true\n"
    )


def launch_command() -> list[str]:
    if getattr(sys, "frozen", False):
        return [str(Path(sys.executable).resolve())]
    return [sys.executable, str(Path(__file__).resolve().parent / "gui.py")]


def is_enabled() -> bool:
    if pt.IS_MAC:
        return PLIST.is_file()
    if pt.IS_LINUX:
        return _is_our_linux_entry()
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Software\Microsoft\Windows\CurrentVersion\Run") as k:
            winreg.QueryValueEx(k, "DesktopKeeper")
        return True
    except OSError:
        return False


def enable() -> None:
    cmd = launch_command()
    if pt.IS_MAC:
        if PLIST.is_symlink():
            raise ValueError(f"Файл автозапуска не должен быть символической ссылкой: {PLIST}")
        PLIST.parent.mkdir(parents=True, exist_ok=True)
        document = plistlib.dumps({
            "Label": LABEL,
            "ProgramArguments": cmd,
            "RunAtLoad": True,
        }, fmt=plistlib.FMT_XML)
        temp_path = None
        try:
            with tempfile.NamedTemporaryFile(
                dir=PLIST.parent, prefix=f".{LABEL}.", suffix=".tmp", delete=False
            ) as temp_file:
                temp_path = Path(temp_file.name)
                temp_file.write(document)
                temp_file.flush()
            temp_path.chmod(0o600)
            PLIST.parent.mkdir(parents=True, exist_ok=True)
            if PLIST.is_symlink():
                raise ValueError(f"Файл автозапуска не должен быть символической ссылкой: {PLIST}")
            temp_path.replace(PLIST)
        finally:
            if temp_path and temp_path.exists():
                temp_path.unlink()
        subprocess.run(["launchctl", "load", "-w", str(PLIST)], check=True)
    elif pt.IS_LINUX:
        if LINUX_AUTOSTART.is_symlink():
            raise ValueError(
                f"Файл автозапуска не должен быть символической ссылкой: "
                f"{LINUX_AUTOSTART}"
            )
        if LINUX_AUTOSTART.exists() and not _is_our_linux_entry():
            raise FileExistsError(
                f"Отказываюсь перезаписывать неизвестный файл автозапуска: "
                f"{LINUX_AUTOSTART}"
            )
        LINUX_AUTOSTART.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        if LINUX_AUTOSTART.parent.is_symlink():
            raise ValueError(
                f"Папка автозапуска не должна быть символической ссылкой: "
                f"{LINUX_AUTOSTART.parent}"
            )
        temp_path = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=LINUX_AUTOSTART.parent,
                prefix=".desktopkeeper.",
                suffix=".tmp",
                delete=False,
            ) as temp_file:
                temp_path = Path(temp_file.name)
                temp_file.write(_linux_autostart_content(cmd))
                temp_file.flush()
            temp_path.chmod(0o600)
            if LINUX_AUTOSTART.is_symlink():
                raise ValueError(
                    f"Файл автозапуска не должен быть символической ссылкой: "
                    f"{LINUX_AUTOSTART}"
                )
            temp_path.replace(LINUX_AUTOSTART)
        finally:
            if temp_path and temp_path.exists():
                temp_path.unlink()
    else:
        import winreg
        value = subprocess.list2cmdline(cmd)
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Software\Microsoft\Windows\CurrentVersion\Run",
                            0, winreg.KEY_SET_VALUE) as k:
            winreg.SetValueEx(k, "DesktopKeeper", 0, winreg.REG_SZ, value)


def disable() -> None:
    if pt.IS_MAC:
        if PLIST.is_symlink():
            raise ValueError(f"Файл автозапуска не должен быть символической ссылкой: {PLIST}")
        if PLIST.is_file():
            subprocess.run(["launchctl", "unload", str(PLIST)], check=True)
            PLIST.unlink()
    elif pt.IS_LINUX:
        if LINUX_AUTOSTART.is_symlink():
            raise ValueError(
                f"Файл автозапуска не должен быть символической ссылкой: "
                f"{LINUX_AUTOSTART}"
            )
        if LINUX_AUTOSTART.exists():
            if not _is_our_linux_entry():
                raise ValueError(
                    f"Отказываюсь удалять неизвестный файл автозапуска: "
                    f"{LINUX_AUTOSTART}"
                )
            LINUX_AUTOSTART.unlink()
    else:
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                                r"Software\Microsoft\Windows\CurrentVersion\Run",
                                0, winreg.KEY_SET_VALUE) as k:
                winreg.DeleteValue(k, "DesktopKeeper")
        except OSError:
            pass