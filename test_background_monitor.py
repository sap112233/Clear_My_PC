import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import background_monitor
import config
import gui
import platform_tools


class BackgroundMonitorTests(unittest.TestCase):
    def test_installer_retention_requires_a_supported_integer(self):
        for value in (True, -1, 10, "15"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                background_monitor.validate_installer_retention(value)
        self.assertEqual(background_monitor.validate_installer_retention(0), 0)
        self.assertEqual(background_monitor.validate_installer_retention(1440), 1440)

    def test_short_ambiguous_names_do_not_arm_automatic_archiving(self):
        self.assertFalse(
            background_monitor.matches_installed_app(Path("VLC-setup.exe"), "VLC")
        )
        self.assertTrue(
            background_monitor.matches_installed_app(
                Path("Example-App-setup.exe"), "Example App"
            )
        )

    def test_pending_installer_queue_rejects_malformed_records(self):
        with self.assertRaises(ValueError):
            background_monitor.validate_pending_installers(
                [{"path": "/tmp/app.exe", "app": "App", "due": "not-a-date"}]
            )
        with self.assertRaisesRegex(ValueError, "локальным"):
            background_monitor.validate_pending_installers(
                [{
                    "path": "/tmp/app.exe",
                    "app": "App",
                    "due": "2026-11-10T12:00:00+00:00",
                }]
            )
        entries = [
            {"path": "/tmp/app.exe", "app": "App", "due": "2026-11-10T12:00:00"},
            {"path": "/tmp/app.exe", "app": "Duplicate", "due": "2026-11-10T12:00:00"},
        ]
        self.assertEqual(
            background_monitor.validate_pending_installers(entries),
            [entries[0]],
        )

    def test_schedule_only_matches_installer_after_app_is_present(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            downloads = Path(temp_dir) / "Downloads"
            downloads.mkdir()
            installer = downloads / "Example Editor-setup.exe"
            installer.write_text("setup", encoding="utf-8")
            pending = []
            now = datetime(2026, 11, 10, 12, 0)

            with mock.patch.object(platform_tools, "INSTALLER_EXTS", {".exe"}):
                self.assertFalse(
                    background_monitor.schedule_installer(
                        pending, installer, "Other App", 15, downloads, [], now
                    )
                )
                self.assertTrue(
                    background_monitor.schedule_installer(
                        pending, installer, "Example Editor", 15, downloads, [], now
                    )
                )
                self.assertEqual(
                    pending[0]["due"],
                    (now + timedelta(minutes=15)).isoformat(),
                )
                self.assertFalse(
                    background_monitor.schedule_installer(
                        pending, installer, "Example Editor", 15, downloads, [], now
                    )
                )

    def test_expired_installer_moves_to_reversible_archive_and_skips_protected(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            downloads = root / "Downloads"
            quarantine = root / "quarantine"
            protected = root / "Protected"
            downloads.mkdir()
            protected.mkdir()
            installer = downloads / "Example-App.exe"
            blocked_installer = downloads / "Protected-App.exe"
            installer.write_text("setup", encoding="utf-8")
            blocked_installer.write_text("blocked", encoding="utf-8")
            now = datetime(2026, 11, 10, 12, 0)
            due = (now - timedelta(minutes=1)).isoformat()
            pending = [
                {"path": str(installer), "app": "Example App", "due": due},
                {
                    "path": str(blocked_installer),
                    "app": "Protected App",
                    "due": due,
                },
            ]
            history = []
            history_path = root / "history.json"

            with mock.patch.object(config, "HISTORY_PATH", history_path), mock.patch.object(
                config, "EXCLUDED_FOLDERS", [blocked_installer]
            ), mock.patch.object(platform_tools, "INSTALLER_EXTS", {".exe"}):
                retained, archived = background_monitor.expire_due_installers(
                    pending,
                    ["Example App", "Protected App"],
                    downloads,
                    quarantine,
                    history,
                    [blocked_installer],
                    now,
                )

            self.assertEqual(retained, [])
            self.assertEqual(len(archived), 1)
            self.assertFalse(installer.exists())
            self.assertEqual(
                archived[0].read_text(encoding="utf-8"), "setup"
            )
            self.assertTrue(blocked_installer.exists())
            self.assertEqual(history[0]["action"], "trash")
            self.assertEqual(history[0]["reason"], "installer_retention")
            self.assertEqual(history[0]["app"], "Example App")

    def test_future_installer_remains_in_queue(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            downloads = root / "Downloads"
            downloads.mkdir()
            installer = downloads / "Example-App.exe"
            installer.write_text("setup", encoding="utf-8")
            now = datetime(2026, 11, 10, 12, 0)
            pending = [{
                "path": str(installer),
                "app": "Example App",
                "due": (now + timedelta(minutes=15)).isoformat(),
            }]

            with mock.patch.object(platform_tools, "INSTALLER_EXTS", {".exe"}):
                retained, archived = background_monitor.expire_due_installers(
                    pending,
                    ["Example App"],
                    downloads,
                    root / "quarantine",
                    [],
                    [],
                    now,
                )

            self.assertEqual(retained, pending)
            self.assertEqual(archived, [])
            self.assertTrue(installer.exists())

    def test_activity_watcher_reports_supported_apps_and_downloaded_installers(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            applications = root / "applications"
            downloads = root / "Downloads"
            applications.mkdir()
            downloads.mkdir()
            launcher = applications / "example.desktop"
            launcher.write_text("[Desktop Entry]\nName=Example\n", encoding="utf-8")
            installer = downloads / "example.deb"
            installer.write_text("package", encoding="utf-8")
            found_apps = []
            found_installers = []
            watcher = gui.ActivityWatcher(
                [applications],
                downloads,
                found_apps.append,
                found_installers.append,
            )

            with mock.patch.object(gui.pt, "IS_LINUX", True), mock.patch.object(
                gui.pt, "IS_MAC", False
            ), mock.patch.object(gui.pt, "IS_WIN", False), mock.patch.object(
                config, "EXCLUDED_FOLDERS", []
            ), mock.patch.object(
                platform_tools, "INSTALLER_EXTS", {".deb"}
            ):
                watcher.on_created(SimpleNamespace(src_path=str(launcher)))
                watcher.on_moved(
                    SimpleNamespace(dest_path=str(installer))
                )

            self.assertEqual(found_apps, [launcher.resolve()])
            self.assertEqual(found_installers, [installer.resolve()])

    def test_activity_watcher_skips_protected_applications(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            applications = root / "applications"
            protected = applications / "protected"
            protected.mkdir(parents=True)
            launcher = protected / "secret.desktop"
            launcher.write_text("[Desktop Entry]\nName=Secret\n", encoding="utf-8")
            found = []
            watcher = gui.ActivityWatcher(
                [applications], root / "Downloads", found.append, found.append
            )

            with mock.patch.object(gui.pt, "IS_LINUX", True), mock.patch.object(
                gui.pt, "IS_MAC", False
            ), mock.patch.object(gui.pt, "IS_WIN", False), mock.patch.object(
                config, "EXCLUDED_FOLDERS", [protected]
            ):
                watcher.on_created(SimpleNamespace(src_path=str(launcher)))

            self.assertEqual(found, [])


if __name__ == "__main__":
    unittest.main()
