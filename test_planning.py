import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest import mock

import gui
import main


def configuration(home: Path) -> dict:
    return {
        "categories": {"Разработка": [], "Игры": [], "Другое": []},
        "features": {
            "screenshots": False,
            "sort_files": True,
            "apps": True,
            "installers": False,
        },
        "enabled_types": ["Книги"],
        "folders": {"musor": "Screens", "apps": "Apps", "files": "Files"},
        "layout_mode": "custom",
        "locations": {
            "screenshots": str(home / "Pictures"),
            "files": str(home / "Documents" / "Sorted"),
            "apps": str(home / "Shortcuts"),
        },
        "managed_roots": {key: [] for key in ("screenshots", "files", "apps")},
        "app_categories": {"com.example.editor": "Разработка"},
        "custom_file_types": {"Книги": [".epub"]},
    }


class PlanningTests(unittest.TestCase):
    def test_application_sources_can_be_nested_beneath_standard_app_roots(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "Applications"
            nested_app = root / "Utilities" / "Example.app"
            nested_app.mkdir(parents=True)

            gui.validate_action_source(
                nested_app, [root], direct_child=False
            )
            with self.assertRaisesRegex(ValueError, "вне разрешённых"):
                gui.validate_action_source(
                    nested_app, [root], direct_child=True
                )

    def test_gui_and_cli_load_legacy_defaults_without_losing_categories(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            home = Path(temp_dir)
            desktop = home / "Desktop"
            desktop.mkdir()
            settings_path = home / "settings.json"
            patches = (
                mock.patch.object(gui.config, "HOME", home),
                mock.patch.object(gui.config, "DESKTOP", desktop),
                mock.patch.object(gui.config, "CONFIG_PATH", settings_path),
            )
            with ExitStack() as stack:
                for patcher in patches:
                    stack.enter_context(patcher)
                gui_settings = gui.load_cfg()
                cli_settings = main.load_user_settings()

            self.assertIn("Графика/дизайн", gui_settings["categories"])
            self.assertEqual(gui_settings["theme"], "light")
            self.assertIn("Другое", gui_settings["categories"])
            self.assertEqual(cli_settings["layout_mode"], "automatic")
            self.assertEqual(gui.config.APPS_ROOT, (desktop / "Apps").resolve())
            self.assertEqual(gui_settings["screenshot_retention_minutes"], 0)
            self.assertEqual(gui_settings["installer_retention_minutes"], 0)
            self.assertFalse(gui_settings["background_monitoring"])
            self.assertEqual(gui_settings["pending_installer_cleanup"], [])
            self.assertEqual(cli_settings["screenshot_retention_minutes"], 0)

    def test_gui_restores_saved_theme_and_rejects_unknown_theme(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            home = Path(temp_dir)
            desktop = home / "Desktop"
            desktop.mkdir()
            settings_path = home / "settings.json"
            settings_path.write_text('{"theme": "dark"}', encoding="utf-8")
            patches = (
                mock.patch.object(gui.config, "HOME", home),
                mock.patch.object(gui.config, "DESKTOP", desktop),
                mock.patch.object(gui.config, "CONFIG_PATH", settings_path),
            )
            with ExitStack() as stack:
                for patcher in patches:
                    stack.enter_context(patcher)
                set_mode = stack.enter_context(
                    mock.patch.object(gui.ctk, "set_appearance_mode")
                )
                self.assertEqual(gui.load_cfg()["theme"], "dark")
                set_mode.assert_called_once_with("dark")

                settings_path.write_text('{"theme": "sepia"}', encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "Тема должна быть"):
                    gui.load_cfg()

    def test_preview_uses_custom_file_types_and_selected_app_category(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            home = Path(temp_dir)
            desktop = home / "Desktop"
            desktop.mkdir()
            app = home / "Applications" / "Editor.app"
            app.mkdir(parents=True)
            book = desktop / "manual.epub"
            book.write_text("book", encoding="utf-8")
            cfg = configuration(home)
            patches = (
                mock.patch.object(gui.config, "HOME", home),
                mock.patch.object(gui.config, "DESKTOP", desktop),
                mock.patch.object(gui.config, "STATE_PATH", home / "state.json"),
                mock.patch.object(gui.utils, "load_json", return_value={"processed": []}),
                mock.patch.object(gui.shots, "collect", return_value=[]),
                mock.patch.object(gui.sorter, "collect", return_value=[(book, "Книги")]),
                mock.patch.object(gui.apps, "scan_applications", return_value=[app]),
                mock.patch.object(gui.apps, "get_app_name", return_value="Editor"),
                mock.patch.object(
                    gui.apps, "get_bundle_id", return_value="com.example.editor"
                ),
                mock.patch.object(gui.pt, "IS_MAC", False),
                mock.patch.object(gui.pt, "IS_LINUX", False),
            )
            with ExitStack() as stack:
                for patcher in patches:
                    stack.enter_context(patcher)
                actions = gui.build_actions(cfg)

            self.assertEqual(len(actions), 2)
            file_action = next(action for action in actions if action["kind"] == "move")
            app_action = next(action for action in actions if action["kind"] == "alias")
            self.assertEqual(
                file_action["dst"],
                (home / "Documents" / "Sorted" / "Книги" / "manual.epub").resolve(),
            )
            self.assertEqual(app_action["dst"], (home / "Shortcuts" / "Разработка" / "Editor.lnk").resolve())
            self.assertEqual(app_action["_category"], "Разработка")

    def test_preview_proposes_reversible_reclassification_of_existing_shortcut(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            home = Path(temp_dir)
            desktop = home / "Desktop"
            desktop.mkdir()
            app = home / "Applications" / "Editor.app"
            app.mkdir(parents=True)
            old_alias = home / "Shortcuts" / "Игры" / "Editor.lnk"
            old_alias.parent.mkdir(parents=True)
            old_alias.write_text("shortcut", encoding="utf-8")
            cfg = configuration(home)
            cfg["features"]["sort_files"] = False
            cfg["app_categories"] = {"com.example.editor": "Разработка"}
            history = [
                {
                    "action": "alias",
                    "src": str(app),
                    "dst": str(old_alias),
                    "app": "Editor",
                    "bundle_id": "com.example.editor",
                    "category": "Игры",
                }
            ]
            patches = (
                mock.patch.object(gui.config, "HOME", home),
                mock.patch.object(gui.config, "DESKTOP", desktop),
                mock.patch.object(gui.config, "STATE_PATH", home / "state.json"),
                mock.patch.object(gui.utils, "load_json", return_value={"processed": ["Editor"]}),
                mock.patch.object(gui.shots, "collect", return_value=[]),
                mock.patch.object(gui.apps, "scan_applications", return_value=[app]),
                mock.patch.object(gui.apps, "get_app_name", return_value="Editor"),
                mock.patch.object(
                    gui.apps, "get_bundle_id", return_value="com.example.editor"
                ),
                mock.patch.object(gui.pt, "IS_MAC", False),
                mock.patch.object(gui.pt, "IS_LINUX", False),
            )
            with ExitStack() as stack:
                for patcher in patches:
                    stack.enter_context(patcher)
                actions = gui.build_actions(cfg, history)

            self.assertEqual(len(actions), 1)
            self.assertEqual(actions[0]["kind"], "alias_move")
            self.assertEqual(actions[0]["src"], old_alias)
            self.assertEqual(
                actions[0]["dst"],
                (home / "Shortcuts" / "Разработка" / "Editor.lnk").resolve(),
            )


if __name__ == "__main__":
    unittest.main()
