"""Кроссплатформенный слой: пути, ярлыки, корзина, активное окно.
macOS и Windows без сторонних библиотек."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

IS_MAC = sys.platform == "darwin"
IS_WIN = sys.platform.startswith("win")

APP_EXT = ".app" if IS_MAC else ".lnk"
INSTALLER_EXTS = {".dmg", ".pkg", ".zip"} if IS_MAC else {".exe", ".msi", ".zip"}


# ---------- Системные папки ----------

def _win_known_folder(guid_str: str) -> Path:
    import ctypes
    from ctypes import byref

    class GUID(ctypes.Structure):
        _fields_ = [("Data1", ctypes.c_uint32), ("Data2", ctypes.c_uint16),
                    ("Data3", ctypes.c_uint16), ("Data4", ctypes.c_char * 8)]

    g = GUID()
    ctypes.windll.ole32.CLSIDFromString(guid_str, byref(g))
    ptr = ctypes.c_wchar_p()
    ctypes.windll.shell32.SHGetKnownFolderPath(byref(g), 0, None, byref(ptr))
    val = ptr.value
    ctypes.windll.ole32.CoTaskMemFree(ptr)
    return Path(val)


def desktop_dir() -> Path:
    if IS_WIN:
        return _win_known_folder("{B4BFCC3A-DB2C-424C-B029-7FE99A87C641}")
    return Path.home() / "Desktop"


def downloads_dir() -> Path:
    if IS_WIN:
        return _win_known_folder("{374DE290-123F-4565-9164-39C4925E467B}")
    return Path.home() / "Downloads"


def app_dirs() -> list[Path]:
    if IS_MAC:
        return [Path("/Applications"), Path.home() / "Applications"]
    import os
    return [
        Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData"))
        / "Microsoft/Windows/Start Menu/Programs",
        Path(os.environ.get("APPDATA", "")) / "Microsoft/Windows/Start Menu/Programs",
    ]


# ---------- Ярлыки / алиасы ----------

def create_shortcut(target: Path, dst_no_ext: Path) -> Path:
    """macOS: алиас Finder. Windows: .lnk (или копия .lnk)."""
    if IS_MAC:
        script = f'''
        tell application "Finder"
            make alias file to (POSIX file "{target}") at (POSIX file "{dst_no_ext.parent}")
        end tell
        '''
        subprocess.run(["osascript", "-e", script], check=True, timeout=10)
        return dst_no_ext
    dst = dst_no_ext.with_suffix(".lnk")
    if target.suffix.lower() == ".lnk":
        import shutil
        shutil.copy2(target, dst)
        return dst
    ps = (
        "$ws = New-Object -ComObject WScript.Shell; "
        f"$sc = $ws.CreateShortcut('{dst}'); "
        f"$sc.TargetPath = '{target}'; $sc.Save()"
    )
    subprocess.run(["powershell", "-NoProfile", "-Command", ps], check=True, timeout=15)
    return dst


# ---------- Корзина ----------

def send_to_trash(path: Path) -> bool:
    if IS_MAC:
        script = f'tell application "Finder" to delete (POSIX file "{path}")'
        subprocess.run(["osascript", "-e", script], check=True, timeout=10)
        return True
    import ctypes
    from ctypes import byref, wintypes

    class SHFILEOPSTRUCT(ctypes.Structure):
        _fields_ = [("hwnd", wintypes.HWND), ("wFunc", ctypes.c_uint),
                    ("pFrom", ctypes.c_wchar_p), ("pTo", ctypes.c_wchar_p),
                    ("fFlags", ctypes.c_ushort),
                    ("fAnyOperationsAborted", wintypes.BOOL),
                    ("hNameMappings", ctypes.c_void_p),
                    ("lpszProgressTitle", ctypes.c_wchar_p)]

    op = SHFILEOPSTRUCT()
    op.wFunc = 3  # FO_DELETE
    op.pFrom = str(path) + "\0"
    op.fFlags = 0x40 | 0x10 | 0x04  # в корзину, без подтверждений, тихо
    return ctypes.windll.shell32.SHFileOperationW(byref(op)) == 0


# ---------- Активное окно (для имён скриншотов) ----------

def frontmost_app() -> tuple[str, str]:
    if IS_MAC:
        script = '''
        tell application "System Events"
            set fp to first application process whose frontmost is true
            set appName to name of fp
            set winTitle to ""
            try
                set winTitle to name of front window of fp
            end try
            return appName & tab & winTitle
        end tell
        '''
        try:
            r = subprocess.run(["osascript", "-e", script],
                               capture_output=True, text=True, timeout=3)
            app, _, title = r.stdout.strip().partition("\t")
            return (app or "Screen", title)
        except Exception:
            return ("Screen", "")
    try:
        import ctypes
        from ctypes import byref, wintypes
        hwnd = ctypes.windll.user32.GetForegroundWindow()
        n = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
        buf = ctypes.create_unicode_buffer(n + 1)
        ctypes.windll.user32.GetWindowTextW(hwnd, buf, n + 1)
        title = buf.value
        pid = wintypes.DWORD()
        ctypes.windll.user32.GetWindowThreadProcessId(hwnd, byref(pid))
        h = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
        exe_buf = ctypes.create_unicode_buffer(260)
        size = wintypes.DWORD(260)
        ctypes.windll.kernel32.QueryFullProcessImageNameW(h, 0, exe_buf, byref(size))
        ctypes.windll.kernel32.CloseHandle(h)
        return (Path(exe_buf.value).stem or "Screen", title)
    except Exception:
        return ("Screen", "")


# ---------- Куда сохраняются скриншоты ----------

def set_screenshot_location(folder: Path) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    if IS_MAC:
        subprocess.run(["defaults", "write", "com.apple.screencapture",
                        "location", str(folder)], check=True)
        subprocess.run(["killall", "SystemUIServer"])
    else:
        import winreg
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders",
            0, winreg.KEY_SET_VALUE,
        ) as key:
            winreg.SetValueEx(key, "{B7BEDE81-DF94-4682-A7D8-57A52620B86F}",
                              0, winreg.REG_EXPAND_SZ, str(folder))
    print(f"OK: место сохранения скриншотов → {folder}")