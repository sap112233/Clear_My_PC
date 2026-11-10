"""Кроссплатформенный слой: пути, ярлыки, корзина, активное окно.
macOS и Windows без сторонних библиотек."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

IS_MAC = sys.platform == "darwin"
IS_WIN = sys.platform.startswith("win")
IS_LINUX = sys.platform.startswith("linux")

APP_EXT = ".app" if IS_MAC else ".lnk" if IS_WIN else ".desktop"
INSTALLER_EXTS = (
    {".dmg", ".pkg", ".zip"}
    if IS_MAC
    else {".exe", ".msi", ".zip"}
    if IS_WIN
    else {".deb", ".rpm", ".appimage", ".zip"}
)


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
    if IS_WIN:
        return [
            Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData"))
            / "Microsoft/Windows/Start Menu/Programs",
            Path(os.environ.get("APPDATA", ""))
            / "Microsoft/Windows/Start Menu/Programs",
        ]
    if IS_LINUX:
        return [
            Path.home() / ".local/share/applications",
            Path("/usr/local/share/applications"),
            Path("/usr/share/applications"),
        ]
    return []


# ---------- Ярлыки / алиасы ----------

def create_shortcut(target: Path, dst_no_ext: Path) -> Path:
    """Create a Finder alias, Windows shortcut, or Linux desktop-entry copy."""
    if not (target.exists() or target.is_symlink()):
        raise FileNotFoundError(target)
    if IS_MAC:
        if dst_no_ext.exists() or dst_no_ext.is_symlink():
            raise FileExistsError(dst_no_ext)
        script = '''
        on run argv
            set targetPath to item 1 of argv
            set destinationPath to item 2 of argv
        tell application "Finder"
            make alias file to (POSIX file targetPath) at (POSIX file destinationPath)
        end tell
        end run
        '''
        dst_no_ext.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["osascript", "-e", script, str(target), str(dst_no_ext.parent)],
            check=True,
            timeout=10,
        )
        return dst_no_ext
    if IS_LINUX:
        if target.is_symlink() or target.suffix.lower() != ".desktop":
            raise ValueError(f"Ожидался файл .desktop: {target}")
        dst = dst_no_ext.with_suffix(".desktop")
        if dst.exists() or dst.is_symlink():
            raise FileExistsError(dst)
        dst.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(dst, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o700)
        try:
            with os.fdopen(fd, "wb") as output, target.open("rb") as source:
                while chunk := source.read(1024 * 1024):
                    output.write(chunk)
                output.flush()
                os.fsync(output.fileno())
        except BaseException:
            dst.unlink(missing_ok=True)
            raise
        return dst
    dst = dst_no_ext.with_suffix(".lnk")
    if dst.exists() or dst.is_symlink():
        raise FileExistsError(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    if target.suffix.lower() == ".lnk":
        import shutil
        shutil.copy2(target, dst)
        return dst
    ps = (
        "$target = $env:DESKTOPKEEPER_TARGET; "
        "$destination = $env:DESKTOPKEEPER_DESTINATION; "
        "$ws = New-Object -ComObject WScript.Shell; "
        "$sc = $ws.CreateShortcut($destination); "
        "$sc.TargetPath = $target; $sc.Save()"
    )
    env = os.environ.copy()
    env["DESKTOPKEEPER_TARGET"] = str(target)
    env["DESKTOPKEEPER_DESTINATION"] = str(dst)
    subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
        env=env,
        check=True,
        timeout=15,
    )
    return dst


# ---------- Корзина ----------

def send_to_trash(path: Path) -> bool:
    if not (path.exists() or path.is_symlink()):
        raise FileNotFoundError(path)
    if IS_MAC:
        script = '''
        on run argv
            tell application "Finder" to delete (POSIX file (item 1 of argv))
        end run
        '''
        subprocess.run(["osascript", "-e", script, str(path)], check=True, timeout=10)
        return True
    if IS_LINUX:
        subprocess.run(
            ["gio", "trash", "--", str(path)],
            check=True,
            timeout=30,
        )
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
    result = ctypes.windll.shell32.SHFileOperationW(byref(op))
    return result == 0 and not op.fAnyOperationsAborted


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
    if IS_MAC:
        folder.mkdir(parents=True, exist_ok=True)
        subprocess.run(["defaults", "write", "com.apple.screencapture",
                        "location", str(folder)], check=True)
        subprocess.run(["killall", "SystemUIServer"])
    elif IS_LINUX:
        raise NotImplementedError(
            "Изменение системной папки скриншотов не поддерживается "
            "для Linux: настройте её средствами вашего окружения рабочего стола."
        )
    else:
        folder.mkdir(parents=True, exist_ok=True)
        import winreg
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders",
            0, winreg.KEY_SET_VALUE,
        ) as key:
            winreg.SetValueEx(key, "{B7BEDE81-DF94-4682-A7D8-57A52620B86F}",
                              0, winreg.REG_EXPAND_SZ, str(folder))
    print(f"OK: место сохранения скриншотов → {folder}")