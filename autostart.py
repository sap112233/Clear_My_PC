"""Автозапуск при входе в систему: macOS (LaunchAgent) и Windows (Run key)."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import platform_tools as pt

LABEL = "com.desktopkeeper"
PLIST = Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"


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
        args = "".join(f"    <string>{a}</string>\n" for a in cmd)
        PLIST.parent.mkdir(parents=True, exist_ok=True)
        PLIST.write_text(f'''<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>{LABEL}</string>
  <key>ProgramArguments</key>
  <array>
{args}  </array>
  <key>RunAtLoad</key><true/>
</dict>
</plist>
''', encoding="utf-8")
        subprocess.run(["launchctl", "load", "-w", str(PLIST)], check=False)
    else:
        import winreg
        value = f'"{cmd[0]}"' if " " in cmd[0] else cmd[0]
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Software\Microsoft\Windows\CurrentVersion\Run",
                            0, winreg.KEY_SET_VALUE) as k:
            winreg.SetValueEx(k, "DesktopKeeper", 0, winreg.REG_SZ, value)


def disable() -> None:
    if pt.IS_MAC:
        subprocess.run(["launchctl", "unload", str(PLIST)], check=False)
        PLIST.unlink(missing_ok=True)
    else:
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                                r"Software\Microsoft\Windows\CurrentVersion\Run",
                                0, winreg.KEY_SET_VALUE) as k:
                winreg.DeleteValue(k, "DesktopKeeper")
        except OSError:
            pass