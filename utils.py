"""Общие утилиты: JSON, имена, перемещения с логом."""
from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
import time
import uuid
from datetime import datetime
from pathlib import Path


def load_json(path: Path, default):
    if path.is_symlink():
        raise ValueError(f"Нельзя читать JSON через символическую ссылку: {path}")
    if path.is_file():
        return json.loads(path.read_text(encoding="utf-8"))
    return default


def save_json(path: Path, data) -> None:
    if path.is_symlink():
        raise ValueError(f"Нельзя перезаписывать JSON через символическую ссылку: {path}")
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temp_file:
            temp_path = Path(temp_file.name)
            json.dump(data, temp_file, ensure_ascii=False, indent=2)
            temp_file.flush()
            os.fsync(temp_file.fileno())
        os.replace(temp_path, path)
    finally:
        if temp_path and temp_path.exists():
            temp_path.unlink()


def sanitize(name: str, max_len: int = 90) -> str:
    name = re.sub(r'[/:\\?*<>|"]', " ", name)
    name = re.sub(r"\s+", " ", name).strip(" .")
    return name[:max_len] or "screen"


def safe_child_path(root: Path, *segments: str) -> Path:
    """Build a path from plain child names and reject traversal or symlink escapes."""
    for segment in segments:
        if (
            not segment
            or segment in {".", ".."}
            or Path(segment).is_absolute()
            or "/" in segment
            or "\\" in segment
            or "\0" in segment
        ):
            raise ValueError(f"Недопустимое имя папки или файла: {segment!r}")
    base = root.resolve()
    candidate = base.joinpath(*segments)
    resolved = candidate.resolve()
    if resolved != base and base not in resolved.parents:
        raise ValueError(f"Путь выходит за пределы папки {base}: {candidate}")
    return candidate


def unique_dst(dst: Path, reserved: set[Path] | None = None) -> Path:
    if reserved is None:
        reserved = set()
    stem, suffix, n = dst.stem, dst.suffix, 2
    while dst.exists() or dst.is_symlink() or dst in reserved:
        dst = dst.with_name(f"{stem} ({n}){suffix}")
        n += 1
    reserved.add(dst)
    return dst


def logged_move(src: Path, dst: Path, history: list, *, allow_unique: bool = True) -> Path:
    import config

    if not (src.exists() or src.is_symlink()):
        raise FileNotFoundError(src)
    if allow_unique:
        dst = unique_dst(dst)
    elif dst.exists() or dst.is_symlink():
        raise FileExistsError(dst)
    entry = {
        "ts": datetime.now().isoformat(),
        "action": "move",
        "src": str(src),
        "dst": str(dst),
        "status": "pending",
    }
    history.append(entry)
    try:
        save_json(config.HISTORY_PATH, history)
    except (OSError, TypeError, ValueError):
        history.remove(entry)
        raise

    try:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))
    except OSError as exc:
        if not (dst.exists() or dst.is_symlink()):
            history.remove(entry)
        else:
            entry["error"] = str(exc)
        save_json(config.HISTORY_PATH, history)
        raise

    entry["status"] = "complete"
    save_json(config.HISTORY_PATH, history)
    return dst


def rollback_entries(
    history: list[dict],
    entries: list[dict],
    state: dict,
    rollback_dir: Path,
    allowed_roots: dict[str, list[Path]],
) -> tuple[int, list[str]]:
    """Revert selected recorded actions without overwriting existing files."""
    history_ids = {id(entry) for entry in history}
    restored = 0
    errors = []

    def is_managed_path(path: Path, roots: list[Path]) -> bool:
        resolved = path.resolve()
        return any(
            resolved != root.resolve() and root.resolve() in resolved.parents
            for root in roots
        )

    for entry in entries:
        if id(entry) not in history_ids or entry.get("undone"):
            continue

        action = entry.get("action")
        try:
            if action in {"move", "trash"}:
                src_value, dst_value = entry.get("src"), entry.get("dst")
                if not src_value or not dst_value:
                    raise ValueError("Для этого действия нет данных для безопасного отката.")
                original, current = Path(src_value), Path(dst_value)
                if not is_managed_path(original, allowed_roots["move_sources"]):
                    raise ValueError(f"Исходный путь вне разрешённых папок: {original}")
                if not is_managed_path(current, allowed_roots["move_destinations"]):
                    raise ValueError(f"Файл назначения вне папок приложения: {current}")
                if (
                    entry.get("status") == "pending"
                    and not (current.exists() or current.is_symlink())
                    and (original.exists() or original.is_symlink())
                ):
                    entry["undone"] = True
                    entry["status"] = "undone"
                    entry["undo_ts"] = datetime.now().isoformat()
                    restored += 1
                    continue
                if not (current.exists() or current.is_symlink()):
                    raise FileNotFoundError(f"Файл после действия не найден: {current}")
                if original.exists() or original.is_symlink():
                    raise FileExistsError(f"Исходный путь уже занят: {original}")
                original.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(current), str(original))
            elif action == "alias":
                alias_value = entry.get("dst") or entry.get("alias")
                if not alias_value:
                    raise ValueError("Для ярлыка не сохранён путь.")
                alias = Path(alias_value)
                if not is_managed_path(alias, allowed_roots["alias_destinations"]):
                    raise ValueError(f"Ярлык находится вне папки приложений: {alias}")
                if not is_managed_path(rollback_dir, allowed_roots["rollback_roots"]):
                    raise ValueError(f"Папка архива отката вне разрешённого хранилища: {rollback_dir}")
                if not (alias.exists() or alias.is_symlink()):
                    raise FileNotFoundError(f"Ярлык не найден: {alias}")
                rollback_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
                archived = unique_dst(rollback_dir / f"{uuid.uuid4().hex}-{alias.name}")
                shutil.move(str(alias), str(archived))
                entry["undo_dst"] = str(archived)
            else:
                raise ValueError(f"Действие «{action}» нельзя откатить.")

            entry["undone"] = True
            entry["status"] = "undone"
            entry["undo_ts"] = datetime.now().isoformat()
            if action == "alias":
                app_marker = entry.get("app") or Path(entry.get("src") or "").stem
                markers = {app_marker, entry.get("bundle_id")}
                markers.discard(None)
                remaining = {
                    marker
                    for item in history
                    if item is not entry and not item.get("undone") and item.get("action") == "alias"
                    for marker in (item.get("app"), item.get("bundle_id"))
                    if marker
                }
                state["processed"] = [
                    marker for marker in state.get("processed", [])
                    if marker not in markers or marker in remaining
                ]
            restored += 1
        except (OSError, RuntimeError, ValueError) as exc:
            errors.append(f"{entry.get('src') or entry.get('app') or 'действие'}: {exc}")

    return restored, errors


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