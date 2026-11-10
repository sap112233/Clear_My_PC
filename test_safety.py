import json
import os
import tempfile
import unittest
from unittest import mock
from pathlib import Path

import app_handler
import autostart
import file_sorter
import notify
import platform_tools
import screenshot_handler
import utils


def allowed_roots(root):
    return {
        "move_sources": [root],
        "move_destinations": [root],
        "alias_destinations": [root],
        "rollback_roots": [root],
    }


class SafetyTests(unittest.TestCase):
    def test_linux_notifications_use_notify_send_without_a_shell(self):
        with mock.patch.object(notify.pt, "IS_LINUX", True), mock.patch.object(
            notify.pt, "IS_MAC", False
        ), mock.patch.object(notify.pt, "IS_WIN", False), mock.patch.object(
            notify.subprocess, "run"
        ) as run:
            notify.notify("Сортировка завершена; «всё безопасно»")

        run.assert_called_once_with(
            [
                "notify-send",
                "--app-name=DesktopKeeper",
                "DesktopKeeper",
                "Сортировка завершена; «всё безопасно»",
            ],
            check=True,
            timeout=10,
        )

    def test_linux_trash_uses_gio_and_propagates_failures(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "file with spaces.txt"
            path.write_text("data", encoding="utf-8")
            with mock.patch.object(platform_tools, "IS_LINUX", True), mock.patch.object(
                platform_tools, "IS_MAC", False
            ), mock.patch.object(
                platform_tools.subprocess, "run"
            ) as run:
                self.assertTrue(platform_tools.send_to_trash(path))

            run.assert_called_once_with(
                ["gio", "trash", "--", str(path)],
                check=True,
                timeout=30,
            )
            self.assertTrue(path.exists())

            with mock.patch.object(platform_tools, "IS_LINUX", True), mock.patch.object(
                platform_tools, "IS_MAC", False
            ), mock.patch.object(
                platform_tools.subprocess,
                "run",
                side_effect=FileNotFoundError("gio"),
            ):
                with self.assertRaises(FileNotFoundError):
                    platform_tools.send_to_trash(path)
            self.assertTrue(path.exists())

    def test_linux_screenshot_location_rejects_unsupported_system_change(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            destination = Path(temp_dir) / "screenshots"
            with mock.patch.object(platform_tools, "IS_LINUX", True), mock.patch.object(
                platform_tools, "IS_MAC", False
            ):
                with self.assertRaisesRegex(NotImplementedError, "Linux"):
                    platform_tools.set_screenshot_location(destination)
            self.assertFalse(destination.exists())

    def test_linux_notification_failure_is_reported_without_breaking_workflow(self):
        with mock.patch.object(notify.pt, "IS_LINUX", True), mock.patch.object(
            notify.pt, "IS_MAC", False
        ), mock.patch.object(notify.pt, "IS_WIN", False), mock.patch.object(
            notify.subprocess, "run", side_effect=FileNotFoundError("notify-send")
        ), self.assertLogs("notify", level="WARNING") as logs:
            notify.notify("Completed")

        self.assertIn("notify-send", logs.output[0])

    def test_linux_autostart_uses_private_xdg_entry_and_can_be_disabled(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            entry = Path(temp_dir) / "autostart" / "desktopkeeper.desktop"
            command = ["/opt/Desktop Keeper/python", "/app path/gui.py"]
            with mock.patch.object(autostart, "LINUX_AUTOSTART", entry), mock.patch.object(
                autostart.pt, "IS_LINUX", True
            ), mock.patch.object(autostart.pt, "IS_MAC", False), mock.patch.object(
                autostart, "launch_command", return_value=command
            ):
                self.assertFalse(autostart.is_enabled())
                autostart.enable()

                self.assertTrue(autostart.is_enabled())
                content = entry.read_text(encoding="utf-8")
                self.assertIn('Exec="/opt/Desktop Keeper/python" "/app path/gui.py"', content)
                self.assertIn("X-DesktopKeeper-Autostart=true", content)
                if os.name == "posix":
                    self.assertEqual(entry.stat().st_mode & 0o777, 0o600)

                autostart.disable()
                self.assertFalse(entry.exists())

    def test_linux_autostart_refuses_to_replace_or_remove_unknown_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            entry = Path(temp_dir) / "desktopkeeper.desktop"
            entry.write_text("[Desktop Entry]\nName=Other App\n", encoding="utf-8")
            with mock.patch.object(autostart, "LINUX_AUTOSTART", entry), mock.patch.object(
                autostart.pt, "IS_LINUX", True
            ), mock.patch.object(autostart.pt, "IS_MAC", False):
                with self.assertRaises(FileExistsError):
                    autostart.enable()
                with self.assertRaises(ValueError):
                    autostart.disable()
            self.assertIn("Other App", entry.read_text(encoding="utf-8"))

    def test_selective_rollback_only_restores_selected_move(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source_a, source_b = root / "a.txt", root / "b.txt"
            moved_a, moved_b = root / "a-moved.txt", root / "b-moved.txt"
            moved_a.write_text("a", encoding="utf-8")
            moved_b.write_text("b", encoding="utf-8")
            first = {"action": "move", "src": str(source_a), "dst": str(moved_a)}
            second = {"action": "move", "src": str(source_b), "dst": str(moved_b)}
            history = [first, second]

            count, errors = utils.rollback_entries(
                history, [first], {}, root / "rollback", allowed_roots(root)
            )

            self.assertEqual((count, errors), (1, []))
            self.assertEqual(source_a.read_text(encoding="utf-8"), "a")
            self.assertTrue(moved_b.exists())
            self.assertTrue(first["undone"])
            self.assertNotIn("undone", second)

    def test_full_rollback_restores_every_selected_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            entries = []
            for name in ("one.txt", "two.txt"):
                destination = root / f"moved-{name}"
                destination.write_text(name, encoding="utf-8")
                entries.append({
                    "action": "move",
                    "src": str(root / name),
                    "dst": str(destination),
                })

            count, errors = utils.rollback_entries(
                entries, entries, {}, root / "rollback", allowed_roots(root)
            )

            self.assertEqual((count, errors), (2, []))
            self.assertEqual(
                [(root / name).read_text(encoding="utf-8") for name in ("one.txt", "two.txt")],
                ["one.txt", "two.txt"],
            )

    def test_move_is_recorded_before_and_after_the_filesystem_change(self):
        import config

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source, destination = root / "source.txt", root / "destination.txt"
            history_path = root / "history.json"
            source.write_text("data", encoding="utf-8")
            history = []

            with mock.patch.object(config, "HISTORY_PATH", history_path):
                result = utils.logged_move(
                    source, destination, history, allow_unique=False
                )

            self.assertEqual(result, destination)
            self.assertFalse(source.exists())
            self.assertEqual(destination.read_text(encoding="utf-8"), "data")
            saved = utils.load_json(history_path, [])
            self.assertEqual(saved[0]["status"], "complete")
            self.assertEqual(saved[0]["dst"], str(destination))

    def test_move_rejects_excluded_destination_without_creating_it(self):
        import config

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "source.txt"
            protected = root / "Protected"
            destination = protected / "Sorted" / "source.txt"
            source.write_text("data", encoding="utf-8")

            with mock.patch.object(config, "EXCLUDED_FOLDERS", [protected]):
                with self.assertRaisesRegex(ValueError, "защищённую"):
                    utils.logged_move(source, destination, [], allow_unique=False)

            self.assertTrue(source.exists())
            self.assertFalse(protected.exists())

    def test_scanners_skip_excluded_desktop_and_downloads(self):
        import config

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            desktop = root / "Desktop"
            downloads = root / "Downloads"
            desktop.mkdir()
            downloads.mkdir()
            (desktop / "photo.png").write_text("image", encoding="utf-8")
            installer = downloads / f"setup{next(iter(platform_tools.INSTALLER_EXTS))}"
            installer.write_text("installer", encoding="utf-8")

            with mock.patch.object(config, "DESKTOP", desktop), mock.patch.object(
                config, "DOWNLOADS", downloads
            ), mock.patch.object(
                config, "EXCLUDED_FOLDERS", [desktop, downloads]
            ):
                self.assertEqual(file_sorter.collect(), [])
                self.assertEqual(app_handler.scan_downloads(), [])

    def test_application_scanner_finds_nested_macos_apps_not_nested_bundle_helpers(self):
        import config

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "Applications"
            group = root / "Creative Tools"
            outer_app = group / "Editor.app"
            helper_app = outer_app / "Contents" / "Helpers" / "Helper.app"
            nested_app = group / "Support" / "Renderer.app"
            helper_app.mkdir(parents=True)
            nested_app.mkdir(parents=True)

            with mock.patch.object(config, "APP_DIRS", [root]), mock.patch.object(
                platform_tools, "IS_MAC", True
            ):
                found = app_handler.scan_applications()

            self.assertEqual(set(found), {outer_app, nested_app})
            self.assertNotIn(helper_app, found)

    def test_application_scanner_finds_nested_windows_start_menu_shortcuts(self):
        import config

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "Programs"
            shortcut = root / "Games" / "Indie" / "Game.lnk"
            shortcut.parent.mkdir(parents=True)
            shortcut.write_text("shortcut", encoding="utf-8")

            with mock.patch.object(config, "APP_DIRS", [root]), mock.patch.object(
                platform_tools, "IS_WIN", True
            ):
                found = app_handler.scan_applications()

            self.assertEqual(found, [shortcut])

    def test_linux_application_scanner_reads_desktop_entries_and_display_name(self):
        import config

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "applications"
            nested = root / "Utilities"
            nested.mkdir(parents=True)
            launcher = nested / "org.example.Editor.desktop"
            launcher.write_text(
                "[Desktop Entry]\nName=Example Editor\nExec=/usr/bin/editor\n",
                encoding="utf-8",
            )

            with mock.patch.object(config, "APP_DIRS", [root]), mock.patch.object(
                platform_tools, "IS_LINUX", True
            ), mock.patch.object(platform_tools, "IS_MAC", False), mock.patch.object(
                platform_tools, "IS_WIN", False
            ):
                found = app_handler.scan_applications()
                name = app_handler.get_app_name(launcher)

            self.assertEqual(found, [launcher])
            self.assertEqual(name, "Example Editor")

    def test_linux_shortcut_copies_desktop_entry_without_overwriting(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "source.desktop"
            destination = root / "Shortcuts" / "Example.desktop"
            content = (
                "[Desktop Entry]\nName=Example\nExec=/usr/bin/example\n"
                "Type=Application\n"
            )
            source.write_text(content, encoding="utf-8")

            with mock.patch.object(platform_tools, "IS_LINUX", True), mock.patch.object(
                platform_tools, "IS_MAC", False
            ):
                created = platform_tools.create_shortcut(source, destination)
                self.assertEqual(created, destination)
                self.assertEqual(destination.read_text(encoding="utf-8"), content)
                if os.name == "posix":
                    self.assertTrue(destination.stat().st_mode & 0o100)
                with self.assertRaises(FileExistsError):
                    platform_tools.create_shortcut(source, destination)

    def test_application_scanner_does_not_follow_excluded_subfolders(self):
        import config

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "Applications"
            protected = root / "Protected"
            allowed = root / "Allowed" / "App.app"
            secret = protected / "Secret.app"
            allowed.mkdir(parents=True)
            secret.mkdir(parents=True)

            with mock.patch.object(config, "APP_DIRS", [root]), mock.patch.object(
                config, "EXCLUDED_FOLDERS", [protected]
            ), mock.patch.object(platform_tools, "IS_MAC", True):
                found = app_handler.scan_applications()

            self.assertEqual(found, [allowed])

    def test_screenshot_retention_archives_expired_files_reversibly(self):
        import config
        from datetime import datetime, timedelta

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            desktop = root / "Desktop"
            musor = root / "мусор"
            quarantine = root / "quarantine"
            desktop.mkdir()
            musor.mkdir()
            expired = desktop / "Screenshot old.png"
            recent = desktop / "Screenshot recent.png"
            expired.write_text("expired", encoding="utf-8")
            recent.write_text("recent", encoding="utf-8")
            now = datetime.now()
            expired_timestamp = (now - timedelta(minutes=16)).timestamp()
            recent_timestamp = (now - timedelta(minutes=5)).timestamp()
            os.utime(expired, (expired_timestamp, expired_timestamp))
            os.utime(recent, (recent_timestamp, recent_timestamp))
            history_path = root / "history.json"
            history = []
            patches = (
                mock.patch.object(config, "DESKTOP", desktop),
                mock.patch.object(config, "MUSOR", musor),
                mock.patch.object(config, "QUARANTINE_DIR", quarantine),
                mock.patch.object(config, "HISTORY_PATH", history_path),
                mock.patch.object(config, "EXCLUDED_FOLDERS", []),
            )
            with patches[0], patches[1], patches[2], patches[3], patches[4]:
                archived = screenshot_handler.expire_old_screenshots(
                    history, 15, now=now
                )

            self.assertEqual(len(archived), 1)
            self.assertFalse(expired.exists())
            self.assertTrue(recent.exists())
            self.assertEqual(archived[0].read_text(encoding="utf-8"), "expired")
            self.assertEqual(history[0]["action"], "trash")
            self.assertEqual(history[0]["reason"], "screenshot_retention")
            self.assertEqual(history[0]["status"], "complete")
            restored, errors = utils.rollback_entries(
                history, [history[0]], {}, root / "rollback", allowed_roots(root)
            )
            self.assertEqual((restored, errors), (1, []))
            self.assertEqual(expired.read_text(encoding="utf-8"), "expired")

    def test_screenshot_retention_tracks_renamed_managed_screenshots(self):
        import config
        from datetime import datetime, timedelta

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            desktop = root / "Desktop"
            musor = root / "мусор"
            quarantine = root / "quarantine"
            desktop.mkdir()
            musor.mkdir()
            renamed = musor / "2026-11-10 18-00.png"
            renamed.write_text("image", encoding="utf-8")
            now = datetime.now()
            old_timestamp = (now - timedelta(minutes=30)).timestamp()
            os.utime(renamed, (old_timestamp, old_timestamp))
            history = [{
                "action": "move",
                "src": str(desktop / "Screenshot capture.png"),
                "dst": str(renamed),
            }]
            patches = (
                mock.patch.object(config, "DESKTOP", desktop),
                mock.patch.object(config, "MUSOR", musor),
                mock.patch.object(config, "QUARANTINE_DIR", quarantine),
                mock.patch.object(config, "HISTORY_PATH", root / "history.json"),
                mock.patch.object(config, "EXCLUDED_FOLDERS", []),
            )
            with patches[0], patches[1], patches[2], patches[3], patches[4]:
                archived = screenshot_handler.expire_old_screenshots(
                    history, 15, now=now
                )

            self.assertEqual(len(archived), 1)
            self.assertFalse(renamed.exists())
            self.assertTrue(archived[0].exists())

    def test_screenshot_retention_is_disabled_and_validates_interval(self):
        import config

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            with mock.patch.object(config, "DESKTOP", root), mock.patch.object(
                config, "MUSOR", root / "мусор"
            ):
                self.assertEqual(screenshot_handler.expire_old_screenshots([], 0), [])
            with self.assertRaisesRegex(ValueError, "срок хранения"):
                screenshot_handler.expire_old_screenshots([], 10)

    def test_alias_move_metadata_is_journaled_before_the_move(self):
        import config

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "Apps" / "Old" / "Example.lnk"
            destination = root / "Apps" / "New" / "Example.lnk"
            source.parent.mkdir(parents=True)
            source.write_text("shortcut", encoding="utf-8")
            history_path = root / "history.json"
            history = []

            with mock.patch.object(config, "HISTORY_PATH", history_path):
                utils.logged_move(
                    source,
                    destination,
                    history,
                    allow_unique=False,
                    action="alias_move",
                    metadata={"app_src": "/Applications/Example.app", "category": "New"},
                )

            self.assertEqual(history[0]["action"], "alias_move")
            self.assertEqual(history[0]["status"], "complete")
            self.assertEqual(history[0]["app_src"], "/Applications/Example.app")
            saved = utils.load_json(history_path, [])
            self.assertEqual(saved[0]["action"], "alias_move")
            self.assertEqual(saved[0]["category"], "New")

    def test_rollback_does_not_overwrite_existing_source(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            original, moved = root / "file.txt", root / "moved.txt"
            original.write_text("new", encoding="utf-8")
            moved.write_text("recorded", encoding="utf-8")
            entry = {"action": "move", "src": str(original), "dst": str(moved)}

            count, errors = utils.rollback_entries(
                [entry], [entry], {}, root / "rollback", allowed_roots(root)
            )

            self.assertEqual(count, 0)
            self.assertEqual(len(errors), 1)
            self.assertEqual(original.read_text(encoding="utf-8"), "new")
            self.assertEqual(moved.read_text(encoding="utf-8"), "recorded")
            self.assertNotIn("undone", entry)

    def test_rollback_rejects_paths_outside_managed_folders(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            managed = root / "managed"
            outside = root / "outside"
            managed.mkdir()
            outside.mkdir()
            original = managed / "original.txt"
            destination = outside / "moved.txt"
            destination.write_text("data", encoding="utf-8")
            entry = {
                "action": "move",
                "src": str(original),
                "dst": str(destination),
            }
            roots = allowed_roots(managed)

            count, errors = utils.rollback_entries(
                [entry], [entry], {}, managed / "rollback", roots
            )

            self.assertEqual(count, 0)
            self.assertEqual(len(errors), 1)
            self.assertTrue(destination.exists())
            self.assertFalse(original.exists())

    def test_rollback_never_touches_a_newly_excluded_folder(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            protected = root / "Protected"
            original = protected / "original.txt"
            destination = protected / "moved.txt"
            protected.mkdir()
            destination.write_text("data", encoding="utf-8")
            entry = {"action": "move", "src": str(original), "dst": str(destination)}

            count, errors = utils.rollback_entries(
                [entry],
                [entry],
                {},
                root / "rollback",
                allowed_roots(root),
                excluded_folders=[protected],
            )

            self.assertEqual(count, 0)
            self.assertEqual(len(errors), 1)
            self.assertTrue(destination.exists())
            self.assertFalse(original.exists())
            self.assertNotIn("undone", entry)

    def test_alias_rollback_archives_shortcut_and_clears_state(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            alias = root / "Apps" / "Example.lnk"
            alias.parent.mkdir()
            alias.write_text("shortcut", encoding="utf-8")
            entry = {
                "action": "alias",
                "app": "Example",
                "bundle_id": "org.example",
                "dst": str(alias),
            }
            state = {"processed": ["Example", "org.example"]}

            count, errors = utils.rollback_entries(
                [entry], [entry], state, root / "rollback", allowed_roots(root)
            )

            self.assertEqual((count, errors), (1, []))
            self.assertFalse(alias.exists())
            self.assertEqual(state["processed"], [])
            self.assertTrue(Path(entry["undo_dst"]).is_file())
            self.assertEqual(Path(entry["undo_dst"]).read_text(encoding="utf-8"), "shortcut")

    def test_alias_move_rollback_restores_shortcut_to_previous_category(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            original = root / "Apps" / "Utilities" / "Example.lnk"
            moved = root / "Apps" / "Development" / "Example.lnk"
            moved.parent.mkdir(parents=True)
            moved.write_text("shortcut", encoding="utf-8")
            entry = {
                "action": "alias_move",
                "src": str(original),
                "dst": str(moved),
                "app_src": "/Applications/Example.app",
            }

            count, errors = utils.rollback_entries(
                [entry], [entry], {}, root / "rollback", allowed_roots(root)
            )

            self.assertEqual((count, errors), (1, []))
            self.assertTrue(original.is_file())
            self.assertFalse(moved.exists())
            self.assertTrue(entry["undone"])

    def test_safe_child_path_rejects_traversal_and_symlink_escape(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "root"
            outside = Path(temp_dir) / "outside"
            root.mkdir()
            outside.mkdir()
            with self.assertRaises(ValueError):
                utils.safe_child_path(root, "../outside")

            link = root / "link"
            try:
                link.symlink_to(outside, target_is_directory=True)
            except OSError:
                self.skipTest("symlinks are unavailable")
            with self.assertRaises(ValueError):
                utils.safe_child_path(root, "link", "file.txt")

    def test_corrupt_json_is_not_silently_replaced(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "history.json"
            path.write_text("{", encoding="utf-8")

            with self.assertRaises(json.JSONDecodeError):
                utils.load_json(path, [])

    def test_json_symlinks_are_rejected(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            target = root / "target.json"
            link = root / "link.json"
            target.write_text("{}", encoding="utf-8")
            try:
                link.symlink_to(target)
            except OSError:
                self.skipTest("symlinks are unavailable")

            with self.assertRaises(ValueError):
                utils.load_json(link, {})
            with self.assertRaises(ValueError):
                utils.save_json(link, {})

    def test_shortcut_paths_are_passed_as_data_not_script_source(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            target = root / "app; Write-Output injected"
            target.write_text("app", encoding="utf-8")
            destination = root / "shortcuts" / "link; Write-Output injected"

            with mock.patch.object(platform_tools, "IS_MAC", True), mock.patch.object(
                platform_tools, "IS_LINUX", False
            ), mock.patch.object(platform_tools.subprocess, "run") as run:
                platform_tools.create_shortcut(target, destination)
                command = run.call_args.args[0]
                self.assertNotIn(str(target), command[2])
                self.assertEqual(command[-2:], [str(target), str(destination.parent)])

            with mock.patch.object(platform_tools, "IS_MAC", False), mock.patch.object(
                platform_tools, "IS_LINUX", False
            ), mock.patch.object(platform_tools.subprocess, "run") as run:
                platform_tools.create_shortcut(target, destination)
                command = run.call_args.args[0]
                environment = run.call_args.kwargs["env"]
                self.assertNotIn(str(target), command[-1])
                self.assertEqual(environment["DESKTOPKEEPER_TARGET"], str(target))
                self.assertEqual(
                    environment["DESKTOPKEEPER_DESTINATION"],
                    str(destination.with_suffix(".lnk")),
                )

    @unittest.skipUnless(os.name == "posix", "POSIX file permissions required")
    def test_json_is_written_atomically_with_private_permissions(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "private.json"

            utils.save_json(path, {"safe": True})

            self.assertEqual(utils.load_json(path, {}), {"safe": True})
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(list(path.parent.glob("*.tmp")), [])


if __name__ == "__main__":
    unittest.main()
