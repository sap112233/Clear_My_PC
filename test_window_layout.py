import unittest
from unittest import mock

import window_layout


class WindowLayoutTests(unittest.TestCase):
    def test_half_and_focus_layouts_cover_screen_without_gaps(self):
        self.assertEqual(
            window_layout.layout_rectangles("half", 1001, 801),
            [(0, 0, 500, 801), (500, 0, 501, 801)],
        )
        self.assertEqual(
            window_layout.layout_rectangles("focus", 1001, 801),
            [(0, 0, 333, 801), (333, 0, 668, 801)],
        )

    def test_grid_layout_covers_screen_without_gaps(self):
        self.assertEqual(
            window_layout.layout_rectangles("grid", 1001, 801),
            [
                (0, 0, 500, 400),
                (500, 0, 501, 400),
                (0, 400, 500, 401),
                (500, 400, 501, 401),
            ],
        )

    def test_rejects_unknown_layouts_and_invalid_screen_sizes(self):
        with self.assertRaises(ValueError):
            window_layout.layout_rectangles("unknown", 1920, 1080)
        with self.assertRaises(ValueError):
            window_layout.layout_rectangles("half", 1, 1080)
        with self.assertRaises(ValueError):
            window_layout.layout_rectangles("half", True, 1080)

    def test_window_matching_uses_process_identity_when_available(self):
        application = {"name": "Visual Studio Code", "path": "/Apps/Code.app"}
        self.assertTrue(
            window_layout._matches_application(
                application, "project.txt", "Code"
            )
        )
        self.assertFalse(
            window_layout._matches_application(
                application, "Visual Studio Code - project.txt", "Finder"
            )
        )

    def test_missing_window_does_not_shift_other_applications_layout(self):
        applications = [
            {"name": "First", "path": "/Apps/First.app"},
            {"name": "Second", "path": "/Apps/Second.app"},
        ]
        windows = [(2, "Second - document", "Second")]

        selected, missing = window_layout._select_windows(applications, windows)

        self.assertEqual(selected, [(2, 1)])
        self.assertEqual(missing, ["First"])

    def test_macos_layout_passes_window_names_as_arguments(self):
        applications = [
            {"name": "First App", "path": "/Apps/First App.app"},
            {"name": "Second App", "path": "/Apps/Second App.app"},
        ]
        with mock.patch.object(
            window_layout.subprocess,
            "run",
            return_value=mock.Mock(stdout="1"),
        ) as run:
            errors = window_layout._arrange_macos(
                applications, "half", (1000, 800)
            )

        self.assertEqual(errors, [])
        self.assertEqual(run.call_args_list[0].args[0][-5:], [
            "First App", "0", "25", "500", "775",
        ])
        self.assertEqual(run.call_args_list[1].args[0][-5:], [
            "Second App", "500", "25", "500", "775",
        ])


if __name__ == "__main__":
    unittest.main()
