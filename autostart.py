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


def launch_command() -> list[str]:
    if getattr(sys, "frozen", False):
        return [str(Path(sys.executable).resolve())]
    return [sys.executable, str(Path(__file__).resolve().parent / "gui.py")]


def is_enabled() -> bool:
    if pt.IS_MAC:
        return PLIST.is_file()
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
    else:
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                                r"Software\Microsoft\Windows\CurrentVersion\Run",
                                0, winreg.KEY_SET_VALUE) as k:
                winreg.DeleteValue(k, "DesktopKeeper")
        except OSError:
            pass