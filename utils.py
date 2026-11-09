"""Общие утилиты: JSON, имена, перемещения с логом."""
import json
import re
import shutil
import time
from datetime import datetime
from pathlib import Path


def load_json(path: Path, default):
    if path.is_file():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            return default
    return default


def save_json(path: Path, data) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def sanitize(name: str, max_len: int = 90) -> str:
    name = re.sub(r'[/:\\?*<>|"]', " ", name)
    name = re.sub(r"\s+", " ", name).strip(" .")
    return name[:max_len] or "screen"


def unique_dst(dst: Path) -> Path:
    stem, suffix, n = dst.stem, dst.suffix, 2
    while dst.exists():
        dst = dst.with_name(f"{stem} ({n}){suffix}")
        n += 1
    return dst


def logged_move(src: Path, dst: Path, history: list) -> Path:
    dst = unique_dst(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), str(dst))
    history.append({
        "ts": datetime.now().isoformat(),
        "action": "move",
        "src": str(src),
        "dst": str(dst),
    })
    return dst


def wait_stable(p: Path, checks: int = 3, delay: float = 0.7) -> bool:
    last = -1
    for _ in range(checks):
        try:
            cur = p.stat().st_size
        except OSError:
            return False
        if cur > 0 and cur == last:
            return True
        last = cur
        time.sleep(delay)
    return True