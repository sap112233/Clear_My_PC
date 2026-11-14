"""Arrange selected work-profile application windows into screen layouts."""
from __future__ import annotations

import ctypes
import re
import subprocess
import time
from pathlib import Path

import platform_tools as pt

WINDOW_WAIT_SECONDS = 8
POLL_INTERVAL_SECONDS = 0.25
_WINDOW_COUNTS = {"half": 2, "focus": 2, "grid": 4}
_APPLE_SCRIPT = """
on run argv
    set processName to item 1 of argv
    set windowX to (item 2 of argv) as integer
    set windowY to (item 3 of argv) as integer
    set windowWidth to (item 4 of argv) as integer
    set windowHeight to (item 5 of argv) as integer
    tell application "System Events"
        if not (exists process processName) then return "0"
        tell process processName
            if (count of windows) is 0 then return "0"
            set position of window 1 to {windowX, windowY}
            set size of window 1 to {windowWidth, windowHeight}
            return "1"
        end tell
    end tell
end run
"""


def layout_rectangles(
    layout: str, width: int, height: int
) -> list[tuple[int, int, int, int]]:
    if layout not in _WINDOW_COUNTS:
        raise ValueError("Выбрана неизвестная раскладка окон.")
    if (
        not isinstance(width, int)
        or isinstance(width, bool)
        or not isinstance(height, int)
        or isinstance(height, bool)
        or width < 2
        or height < 2
    ):
        raise ValueError("Размеры экрана должны быть положительными целыми числами.")

    if layout == "half":
        left = width // 2
        return [(0, 0, left, height), (left, 0, width - left, height)]
    if layout == "focus":
        left = width // 3
        return [(0, 0, left, height), (left, 0, width - left, height)]

    left, top = width // 2, height // 2
    return [
        (0, 0, left, top),
        (left, 0, width - left, top),
        (0, top, left, height - top),
        (left, top, width - left, height - top),
    ]


def arrange_profile(
    profile: dict, screen_size: tuple[int, int]
) -> list[str]:
    layout = profile.get("layout", "none")
    if layout == "none":
        return []
    try:
        layout_rectangles(layout, *screen_size)
        applications = profile["apps"]
        if pt.IS_MAC:
            return _arrange_macos(applications, layout, screen_size)
        if pt.IS_WIN:
            return _arrange_windows(applications, layout)
        if pt.IS_LINUX:
            return _arrange_linux(applications, layout)
        return ["Раскладка окон не поддерживается этой операционной системой."]
    except (OSError, RuntimeError, subprocess.SubprocessError, TypeError, ValueError) as exc:
        details = exc.stderr.strip() if isinstance(
            exc, subprocess.CalledProcessError
        ) and exc.stderr else str(exc)
        return [f"Не удалось расположить окна: {details}"]


def _arrange_macos(
    applications: list[dict],
    layout: str,
    screen_size: tuple[int, int],
) -> list[str]:
    screen_width, screen_height = screen_size
    menu_bar_height = 25
    usable_height = max(1, screen_height - menu_bar_height)
    rectangles = layout_rectangles(layout, screen_width, usable_height)
    errors = []
    for application, (x, y, width, height) in zip(applications, rectangles):
        y += menu_bar_height
        try:
            result = subprocess.run(
                [
                    "osascript",
                    "-e",
                    _APPLE_SCRIPT,
                    "--",
                    application["name"],
                    str(x),
                    str(y),
                    str(min(width, screen_width - x)),
                    str(height),
                ],
                capture_output=True,
                check=True,
                text=True,
                timeout=10,
            )
            if result.stdout.strip() != "1":
                raise RuntimeError("у приложения нет открытого окна.")
        except subprocess.CalledProcessError as exc:
            errors.append(
                f"{application['name']}: {exc.stderr.strip() or str(exc)}"
            )
        except (OSError, subprocess.SubprocessError, RuntimeError) as exc:
            errors.append(f"{application['name']}: {exc}")
    return errors


def _normalized_words(value: str) -> set[str]:
    return {
        word.casefold()
        for word in re.findall(r"[^\W_]+", value, flags=re.UNICODE)
        if len(word) >= 3
    }


def _matches_application(application: dict, title: str, process_name: str) -> bool:
    expected = _normalized_words(application["name"])
    expected.update(_normalized_words(Path(application["path"]).stem))
    process_words = _normalized_words(process_name)
    if process_name:
        return bool(expected.intersection(process_words))
    normalized_title = "".join(re.findall(r"[^\W_]+", title, flags=re.UNICODE)).casefold()
    names = (application["name"], Path(application["path"]).stem)
    return any(
        normalized_name
        and normalized_title.startswith(normalized_name)
        for normalized_name in (
            "".join(re.findall(r"[^\W_]+", name, flags=re.UNICODE)).casefold()
            for name in names
        )
    )


def _select_windows(
    applications: list[dict],
    windows: list[tuple[object, str, str]],
) -> tuple[list[tuple[object, int]], list[str]]:
    selected = []
    missing = []
    used = set()
    for application_index, application in enumerate(applications):
        for identity, title, process_name in windows:
            if identity not in used and _matches_application(
                application, title, process_name
            ):
                selected.append((identity, application_index))
                used.add(identity)
                break
        else:
            missing.append(application["name"])
    return selected, missing


def _wait_for_windows(
    applications: list[dict], list_windows
) -> tuple[list[tuple[object, int]], list[str]]:
    deadline = time.monotonic() + WINDOW_WAIT_SECONDS
    while True:
        selected, missing = _select_windows(applications, list_windows())
        if not missing or time.monotonic() >= deadline:
            return selected, missing
        time.sleep(POLL_INTERVAL_SECONDS)


def _windows_work_area() -> tuple[int, int, int, int]:
    from ctypes import wintypes

    area = wintypes.RECT()
    if not ctypes.windll.user32.SystemParametersInfoW(
        0x0030, 0, ctypes.byref(area), 0
    ):
        raise OSError("не удалось определить рабочую область экрана.")
    return (
        area.left,
        area.top,
        area.right - area.left,
        area.bottom - area.top,
    )


def _windows_list() -> list[tuple[int, str, str]]:
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    windows = []

    def collect(hwnd, _):
        if not user32.IsWindowVisible(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if not length:
            return True
        title = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, title, length + 1)
        process_id = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(process_id))
        process_name = ""
        process = kernel32.OpenProcess(0x1000, False, process_id.value)
        if process:
            try:
                image_path = ctypes.create_unicode_buffer(32768)
                size = wintypes.DWORD(len(image_path))
                if kernel32.QueryFullProcessImageNameW(
                    process, 0, image_path, ctypes.byref(size)
                ):
                    process_name = Path(image_path.value).stem
            finally:
                kernel32.CloseHandle(process)
        windows.append((int(hwnd), title.value, process_name))
        return True

    callback = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)(
        collect
    )
    if not user32.EnumWindows(callback, 0):
        raise OSError("не удалось получить список окон.")
    return windows


def _windows_move(
    hwnd: int, rectangle: tuple[int, int, int, int], origin: tuple[int, int]
) -> None:
    x, y, width, height = rectangle
    origin_x, origin_y = origin
    if not ctypes.windll.user32.SetWindowPos(
        hwnd,
        None,
        origin_x + x,
        origin_y + y,
        width,
        height,
        0x0004 | 0x0010,
    ):
        raise OSError(
            f"системный вызов SetWindowPos завершился ошибкой "
            f"(код {ctypes.get_last_error()})."
        )


def _arrange_windows(
    applications: list[dict],
    layout: str,
) -> list[str]:
    origin_x, origin_y, width, height = _windows_work_area()
    work_rectangles = layout_rectangles(layout, width, height)
    windows, missing = _wait_for_windows(applications, _windows_list)
    errors = [f"{name}: окно не найдено." for name in missing]
    for hwnd, application_index in windows:
        try:
            _windows_move(
                hwnd, work_rectangles[application_index], (origin_x, origin_y)
            )
        except OSError as exc:
            errors.append(str(exc))
    return errors


def _linux_work_area() -> tuple[int, int, int, int]:
    result = subprocess.run(
        ["wmctrl", "-d"],
        capture_output=True,
        check=True,
        text=True,
        timeout=5,
    )
    for line in result.stdout.splitlines():
        match = re.search(r"\bWA:\s*(-?\d+),(-?\d+)\s+(\d+)x(\d+)", line)
        if match:
            return tuple(map(int, match.groups()))
    raise RuntimeError("не удалось определить рабочую область X11.")


def _linux_windows() -> list[tuple[str, str, str]]:
    result = subprocess.run(
        ["wmctrl", "-l", "-p"],
        capture_output=True,
        check=True,
        text=True,
        timeout=5,
    )
    windows = []
    for line in result.stdout.splitlines():
        parts = line.split(maxsplit=4)
        if len(parts) != 5 or not re.fullmatch(r"0x[0-9a-fA-F]+", parts[0]):
            continue
        try:
            process_id = int(parts[2])
        except ValueError:
            continue
        try:
            process_name = Path(f"/proc/{process_id}/exe").resolve().name
        except OSError:
            process_name = ""
        windows.append((parts[0], parts[4], Path(process_name).stem))
    return windows


def _arrange_linux(
    applications: list[dict],
    layout: str,
) -> list[str]:
    origin_x, origin_y, width, height = _linux_work_area()
    work_rectangles = layout_rectangles(layout, width, height)
    windows, missing = _wait_for_windows(applications, _linux_windows)
    errors = [f"{name}: окно не найдено." for name in missing]
    for window_id, application_index in windows:
        if not re.fullmatch(r"0x[0-9a-fA-F]+", str(window_id)):
            errors.append("Пропускаю окно с некорректным идентификатором.")
            continue
        x, y, window_width, window_height = work_rectangles[application_index]
        try:
            subprocess.run(
                [
                    "wmctrl",
                    "-i",
                    "-r",
                    str(window_id),
                    "-e",
                    f"0,{origin_x + x},{origin_y + y},{window_width},{window_height}",
                ],
                capture_output=True,
                check=True,
                text=True,
                timeout=5,
            )
        except subprocess.CalledProcessError as exc:
            errors.append(exc.stderr.strip() or str(exc))
        except (OSError, subprocess.SubprocessError) as exc:
            errors.append(str(exc))
    return errors
