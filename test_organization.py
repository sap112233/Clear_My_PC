import tempfile
import unittest
from pathlib import Path

import organization
from file_sorter import TYPE_MAP


class OrganizationTests(unittest.TestCase):
    def test_screenshot_folder_choice_keeps_default_empty_until_confirmed(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            home = Path(temp_dir)
            desktop = home / "Desktop"
            desktop.mkdir()
            cfg = {
                "features": {"screenshots": True},
                "folders": {"musor": "мусор", "apps": "Apps", "files": "Файлы"},
                "layout_mode": "automatic",
                "locations": {},
            }

            organization.configure_screenshot_folder(
                cfg, "desktop", None, desktop, home
            )

            self.assertTrue(cfg["features"]["screenshots"])
            self.assertEqual(cfg["layout_mode"], "automatic")
            self.assertFalse((desktop / "мусор").exists())
            self.assertFalse((desktop / "Apps").exists())
            self.assertFalse((desktop / "Файлы").exists())

    def test_screenshot_folder_can_use_existing_path_or_be_disabled(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            home = Path(temp_dir)
            desktop = home / "Desktop"
            selected = home / "Pictures" / "Saved Screenshots"
            desktop.mkdir()
            selected.mkdir(parents=True)
            cfg = {
                "features": {"screenshots": True},
                "folders": {"musor": "мусор", "apps": "Apps", "files": "Файлы"},
                "layout_mode": "automatic",
                "locations": {},
            }

            organization.configure_screenshot_folder(
                cfg, "existing", str(selected), desktop, home
            )

            self.assertEqual(cfg["layout_mode"], "custom")
            self.assertEqual(
                cfg["locations"]["screenshots"], str(selected.resolve())
            )
            self.assertFalse((desktop / "Apps").exists())
            self.assertFalse((desktop / "Файлы").exists())

            organization.configure_screenshot_folder(
                cfg, "leave", None, desktop, home
            )
            self.assertFalse(cfg["features"]["screenshots"])

    def test_screenshot_folder_choice_rejects_missing_or_unsafe_paths(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            home = Path(temp_dir) / "home"
            desktop = home / "Desktop"
            home.mkdir()
            desktop.mkdir()
            cfg = {
                "features": {"screenshots": True},
                "folders": {"musor": "мусор", "apps": "Apps", "files": "Файлы"},
                "layout_mode": "automatic",
                "locations": {},
            }

            with self.assertRaisesRegex(ValueError, "не существует"):
                organization.configure_screenshot_folder(
                    cfg, "existing", str(home / "Missing"), desktop, home
                )
            with tempfile.TemporaryDirectory() as outside:
                outside_folder = Path(outside) / "Screens"
                outside_folder.mkdir()
                with self.assertRaisesRegex(ValueError, "внутри домашней"):
                    organization.configure_screenshot_folder(
                        cfg, "existing", str(outside_folder), desktop, home
                    )

    def test_graphic_project_types_and_legacy_enabled_type_migration(self):
        self.assertEqual(
            organization.file_category_for(Path("logo.SVG"), TYPE_MAP, {}),
            "Графические проекты",
        )
        self.assertEqual(
            organization.file_category_for(Path("poster.psd"), TYPE_MAP, {}),
            "Графические проекты",
        )
        self.assertEqual(
            organization.file_category_for(Path("photo.png"), TYPE_MAP, {}),
            "Изображения",
        )

        settings = {"enabled_types": ["Изображения", "Документы"]}
        organization.migrate_enabled_file_types(settings)
        self.assertEqual(
            settings["enabled_types"],
            ["Изображения", "Документы", "Графические проекты"],
        )
        organization.migrate_enabled_file_types(settings)
        self.assertEqual(settings["enabled_types"].count("Графические проекты"), 1)

    def test_graphic_project_migration_preserves_user_disabled_types(self):
        settings = {"enabled_types": ["Документы"]}

        organization.migrate_enabled_file_types(settings)

        self.assertEqual(settings["enabled_types"], ["Документы"])

    def test_excluded_folders_match_the_folder_and_all_descendants(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            protected = Path(temp_dir) / "Projects"
            child = protected / "private.txt"
            unrelated = Path(temp_dir) / "Downloads" / "setup.exe"
            excluded = organization.validate_excluded_folders(
                [str(protected), str(protected / ".")]
            )

            self.assertEqual(excluded, [protected.resolve()])
            self.assertTrue(organization.is_excluded_path(protected, excluded))
            self.assertTrue(organization.is_excluded_path(child, excluded))
            self.assertFalse(organization.is_excluded_path(unrelated, excluded))

    def test_excluded_folder_paths_must_be_absolute_and_not_drive_roots(self):
        with self.assertRaisesRegex(ValueError, "абсолютным"):
            organization.validate_excluded_folders(["relative/path"])
        with self.assertRaisesRegex(ValueError, "корень диска"):
            organization.validate_excluded_folders([str(Path("/"))])

    def test_custom_destinations_must_be_distinct_and_inside_home(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            home = Path(temp_dir) / "home"
            home.mkdir()
            folders = {
                "screenshots": str(home / "Pictures" / "Sorted"),
                "files": str(home / "Documents" / "Sorted"),
                "apps": str(home / "Applications" / "Sorted"),
            }
            cfg = {"layout_mode": "custom", "locations": folders}

            paths = organization.resolve_locations(cfg, home / "Desktop", home)

            self.assertEqual(paths["files"], Path(folders["files"]).resolve())
            cfg["locations"]["apps"] = folders["files"]
            with self.assertRaisesRegex(ValueError, "должны различаться"):
                organization.resolve_locations(cfg, home / "Desktop", home)
            cfg["locations"]["apps"] = str(Path(temp_dir) / "outside")
            with self.assertRaisesRegex(ValueError, "внутри домашней"):
                organization.resolve_locations(cfg, home / "Desktop", home)
            cfg["locations"]["apps"] = str(home / ".desktop-keeper" / "data")
            with self.assertRaisesRegex(ValueError, "папку данных"):
                organization.resolve_locations(cfg, home / "Desktop", home)

    def test_default_destinations_keep_legacy_desktop_folder_names(self):
        desktop = Path("/home/example/Desktop")
        locations = organization.default_locations(
            desktop, {"musor": "Screens", "apps": "Shortcuts", "files": "Sorted"}
        )

        self.assertEqual(locations["screenshots"], (desktop / "Screens").resolve())
        self.assertEqual(locations["apps"], (desktop / "Shortcuts").resolve())
        self.assertEqual(locations["files"], (desktop / "Sorted").resolve())

    def test_custom_file_types_are_validated_and_classified(self):
        definitions = organization.validate_custom_file_types(
            {"Книги": ["epub", ".mobi"]}, TYPE_MAP
        )

        self.assertEqual(
            organization.file_category_for(Path("novel.EPUB"), TYPE_MAP, definitions),
            "Книги",
        )
        with self.assertRaisesRegex(ValueError, "уже используется"):
            organization.validate_custom_file_types({"Images": [".png"]}, TYPE_MAP)
        with self.assertRaisesRegex(ValueError, "занятое имя типа"):
            organization.validate_custom_file_types({"код": [".epub"]}, TYPE_MAP)
        with self.assertRaisesRegex(ValueError, "нескольким типам"):
            organization.validate_custom_file_types(
                {"Книги": [".epub"], "Другие книги": [".epub"]}, TYPE_MAP
            )
        with self.assertRaises(ValueError):
            organization.validate_custom_file_types({"../bad": [".epub"]}, TYPE_MAP)

    def test_app_destinations_use_safe_category_segments(self):
        root = Path("/tmp/desktop-keeper")

        self.assertEqual(
            organization.app_destination(root, "Разработка", "Editor", True),
            (root / "Разработка" / "Editor").resolve(),
        )
        self.assertEqual(
            organization.app_destination(root, "Разработка", "Editor", False),
            (root / "Разработка" / "Editor.lnk").resolve(),
        )
        self.assertEqual(
            organization.app_destination(
                root, "Разработка", "Editor", False, is_linux=True
            ),
            (root / "Разработка" / "Editor.desktop").resolve(),
        )
        self.assertEqual(
            organization.app_destination(root, "Разработка", "Editor.v2", False),
            (root / "Разработка" / "Editor.v2.lnk").resolve(),
        )
        destination = organization.app_destination(root, "../outside", "Editor", True)
        self.assertEqual(destination.parent.parent, root.resolve())

    def test_slash_in_category_label_maps_to_a_safe_folder_name(self):
        root = Path("/tmp/desktop-keeper")

        self.assertEqual(
            organization.app_destination(root, "Графика/дизайн", "Editor", True),
            (root / "Графика дизайн" / "Editor").resolve(),
        )

    def test_active_alias_tracks_relocations_and_selective_rollback(self):
        source = "/Applications/Example.app"
        first = Path("/home/example/Desktop/Apps/Utilities/Example")
        second = Path("/home/example/Desktop/Apps/Development/Example")
        history = [
            {"action": "alias", "src": source, "dst": str(first), "category": "Utilities"},
            {
                "action": "alias_move",
                "app_src": source,
                "src": str(first),
                "dst": str(second),
                "category": "Development",
            },
        ]

        self.assertEqual(
            organization.active_aliases(history)[str(Path(source).resolve())]["path"],
            second,
        )
        history[-1]["undone"] = True
        self.assertEqual(
            organization.active_aliases(history)[str(Path(source).resolve())]["path"],
            first,
        )


if __name__ == "__main__":
    unittest.main()
