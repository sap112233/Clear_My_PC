import tempfile
import unittest
from pathlib import Path

import organization
from file_sorter import TYPE_MAP


class OrganizationTests(unittest.TestCase):
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
