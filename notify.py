"""Системные уведомления: macOS (osascript) и Windows (Toast через PowerShell)."""
from __future__ import annotations

import subprocess

import platform_tools as pt

TITLE = "DesktopKeeper"


def notify(text: str) -> None:
    try:
        safe = text.replace('"', "'").replace("'", "''") if pt.IS_WIN else text.replace('"', "'")
        if pt.IS_MAC:
            subprocess.run(["osascript", "-e",
                            f'display notification "{safe}" with title "{TITLE}"'],
                           check=False, timeout=5)
        elif pt.IS_WIN:
            ps = f"""
            [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
            $t = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02)
            $nodes = $t.GetElementsByTagName('text')
            $nodes.Item(0).AppendChild($t.CreateTextNode('{TITLE}')) | Out-Null
            $nodes.Item(1).AppendChild($t.CreateTextNode('{safe}')) | Out-Null
            $n = [Windows.UI.Notifications.ToastNotification]::new($t)
            [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('DesktopKeeper').Show($n)
            """
            subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                           check=False, timeout=10)
    except Exception:
        pass