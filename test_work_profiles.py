import tempfile
import unittest
from pathlib import Path
from unittest import mock

import work_profiles


class WorkProfileTests(unittest.TestCase):
    def test_validate_profiles_keeps_apps_and_http_websites(self):
        profile = {
            "name": "Дизайн",
            "apps": [{"name": "Figma", "path": "/Applications/Figma.app"}],
            "websites": [
                {"name": "Pinterest", "url": "https://pinterest.com/"}
            ],
        }

        self.assertEqual(work_profiles.validate_profiles([profile]), [profile])

    def test_validate_profiles_rejects_duplicate_names_and_non_web_urls(self):
        with self.assertRaisesRegex(ValueError, "уже существует"):
            work_profiles.validate_profiles([
                {"name": "Дизайн"},
                {"name": "дизайн"},
            ])
        with self.assertRaisesRegex(ValueError, "http://"):
            work_profiles.validate_profiles([{
                "name": "Дизайн",
                "websites": [{"name": "Bad", "url": "javascript:alert(1)"}],
            }])
        with self.assertRaisesRegex(ValueError, "http://"):
            work_profiles.validate_website("https://user:pass@example.com")

    def test_launch_profile_opens_selected_apps_and_websites(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "Applications"
            app = root / "Editor.app"
            app.mkdir(parents=True)
            profile = {
                "name": "Дизайн",
                "apps": [{"name": "Editor", "path": str(app)}],
                "websites": [
                    {"name": "Pinterest", "url": "https://pinterest.com/"}
                ],
            }
            with (
                mock.patch.object(work_profiles.pt, "app_dirs", return_value=[root]),
                mock.patch.object(work_profiles.pt, "IS_MAC", True),
                mock.patch.object(work_profiles.pt, "IS_WIN", False),
                mock.patch.object(work_profiles.pt, "IS_LINUX", False),
                mock.patch.object(work_profiles.subprocess, "Popen") as popen,
                mock.patch.object(work_profiles.webbrowser, "open", return_value=True) as open_url,
            ):
                errors = work_profiles.launch_profile(profile)

            self.assertEqual(errors, [])
            popen.assert_called_once_with(["open", "-a", str(app.resolve())])
            open_url.assert_called_once_with("https://pinterest.com/", new=2)

    def test_launch_profile_reports_missing_or_untrusted_app_and_keeps_going(self):
        profile = {
            "name": "Работа",
            "apps": [
                {"name": "Missing", "path": "/Applications/Missing.app"},
                {"name": "Outside", "path": "/tmp/Outside.app"},
            ],
            "websites": [{"name": "Site", "url": "https://example.com"}],
        }
        with (
            mock.patch.object(
                work_profiles.pt, "app_dirs", return_value=[Path("/Applications")]
            ),
            mock.patch.object(work_profiles.pt, "IS_MAC", True),
            mock.patch.object(work_profiles.pt, "IS_WIN", False),
            mock.patch.object(work_profiles.pt, "IS_LINUX", False),
            mock.patch.object(work_profiles.webbrowser, "open", return_value=True) as open_url,
        ):
            errors = work_profiles.launch_profile(profile)

        self.assertEqual(len(errors), 2)
        self.assertIn("Missing", errors[0])
        self.assertIn("Outside", errors[1])
        open_url.assert_called_once()

    def test_linux_application_launch_uses_gio_with_the_installed_entry_path(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "applications"
            root.mkdir()
            app = root / "editor.desktop"
            app.write_text("[Desktop Entry]\nName=Editor\n", encoding="utf-8")
            with (
                mock.patch.object(work_profiles.pt, "app_dirs", return_value=[root]),
                mock.patch.object(work_profiles.pt, "IS_MAC", False),
                mock.patch.object(work_profiles.pt, "IS_WIN", False),
                mock.patch.object(work_profiles.pt, "IS_LINUX", True),
                mock.patch.object(work_profiles.subprocess, "Popen") as popen,
            ):
                work_profiles.launch_application(str(app))

        popen.assert_called_once_with(["gio", "launch", str(app.resolve())])

    def test_windows_application_launch_uses_startfile_for_installed_shortcut(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "Programs"
            root.mkdir()
            app = root / "Editor.lnk"
            app.touch()
            with (
                mock.patch.object(work_profiles.pt, "app_dirs", return_value=[root]),
                mock.patch.object(work_profiles.pt, "IS_MAC", False),
                mock.patch.object(work_profiles.pt, "IS_WIN", True),
                mock.patch.object(work_profiles.pt, "IS_LINUX", False),
                mock.patch.object(work_profiles.os, "startfile", create=True) as startfile,
            ):
                work_profiles.launch_application(str(app))

        startfile.assert_called_once_with(str(app.resolve()))


if __name__ == "__main__":
    unittest.main()
