"""Проверка обновлений через GitHub Releases (без своего сервера)."""
from __future__ import annotations

import json
import urllib.request
import webbrowser

REPO = "sap112233/Clear_My_PC"
API_URL = f"https://api.github.com/repos/{REPO}/releases/latest"


def current_version() -> tuple:
    from version import VERSION
    return tuple(int(x) for x in VERSION.split("."))


def latest_release() -> dict | None:
    try:
        req = urllib.request.Request(API_URL, headers={"User-Agent": "DesktopKeeper"})
        with urllib.request.urlopen(req, timeout=6) as r:
            data = json.load(r)
        tag = str(data.get("tag_name", "")).lstrip("v")
        ver = tuple(int(x) for x in tag.split("."))
        return {"version": ver, "tag": data.get("tag_name", ""),
                "url": data.get("html_url", ""), "notes": data.get("body", "")}
    except Exception:
        return None


def check_update() -> dict | None:
    rel = latest_release()
    if rel and rel["version"] > current_version():
        return rel
    return None


def open_release(url: str) -> None:
    webbrowser.open(url)