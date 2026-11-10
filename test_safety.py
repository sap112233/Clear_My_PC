import json
import os
import tempfile
import unittest
from unittest import mock
from pathlib import Path

import platform_tools
import utils


def allowed_roots(root):
    return {
        "move_sources": [root],
        "move_destinations": [root],
        "alias_destinations": [root],
        "rollback_roots": [root],
    }


class SafetyTests(unittest.TestCase):
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
            target = root / 'app"; injected'
            target.write_text("app", encoding="utf-8")
            destination = root / "shortcuts" / 'link"; injected'

            with mock.patch.object(platform_tools, "IS_MAC", True), mock.patch.object(
                platform_tools.subprocess, "run"
            ) as run:
                platform_tools.create_shortcut(target, destination)
                command = run.call_args.args[0]
                self.assertNotIn(str(target), command[2])
                self.assertEqual(command[-2:], [str(target), str(destination.parent)])

            with mock.patch.object(platform_tools, "IS_MAC", False), mock.patch.object(
                platform_tools.subprocess, "run"
            ) as run:
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
