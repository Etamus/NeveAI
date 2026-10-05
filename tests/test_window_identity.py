import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

if sys.platform == "win32":
    import neve_window as window


@unittest.skipUnless(sys.platform == "win32", "Windows window controller")
class WindowIdentityTests(unittest.TestCase):
    def test_frame_theme_is_configured_without_geometry_or_focus_changes(self):
        with patch.object(window, "_dwmapi") as dwm, patch.object(window, "_user32") as api:
            dwm.DwmSetWindowAttribute.return_value = -1
            window._prepare_frame_theme(1)
            settings = {
                call.args[1]: call.args[2]._obj.value
                for call in dwm.DwmSetWindowAttribute.call_args_list
            }
            self.assertEqual(settings, {20: 1, 34: 0x383838, 35: 0x231F1F, 36: 0xCCCCCC, 38: 1})
            self.assertTrue(all(call.args[0] == 1 for call in dwm.DwmSetWindowAttribute.call_args_list))
            api.SetWindowPos.assert_not_called()
            api.SetForegroundWindow.assert_not_called()

    def test_frame_colors_are_configured_once_before_the_window_is_shown(self):
        order = []
        with patch.object(window, "_find_app_window", return_value=1), patch.object(
            window, "_user32"
        ) as api, patch.object(window, "_prepare_frame_theme", side_effect=lambda _: order.append("theme")), patch.object(
            window, "_hide_caption_icon"
        ), patch.object(window, "_window_title", return_value=window._WINDOW_READY_TITLE), patch.object(
            window, "_clear_caption_text"
        ), patch.object(window, "_apply_window_state", side_effect=lambda *_: order.append("show")), patch.object(
            window, "_activate_window", side_effect=lambda _: order.append("activate")
        ), patch.object(window.time, "sleep"):
            self.assertEqual(window._bring_app_to_front(timeout=1), 1)
            self.assertEqual(order, ["theme", "show", "activate"])
            api.ShowWindow.assert_called_once_with(1, window._SW_HIDE)

    def test_identity_guard_does_not_reapply_frame_theme_on_focus(self):
        with patch.object(window, "_user32") as api, patch.object(window, "_hide_caption_icon"), patch.object(
            window, "_clear_caption_text"
        ), patch.object(window.time, "sleep"), patch.object(window, "_prepare_frame_theme") as theme:
            api.IsWindow.side_effect = [True, False]
            window._guard_window_identity(1)
            theme.assert_not_called()

    def test_app_keeps_rendering_when_covered_without_disabling_gpu(self):
        with patch.object(window, "_find_chromium_browser", return_value="brave.exe"), patch.object(
            window, "_prepare_browser_profile"
        ), patch.object(window.os, "makedirs"), patch.object(
            window, "_load_window_state", return_value=None
        ), patch.object(window.subprocess, "Popen") as launch, patch.object(
            window, "_bring_app_to_front", return_value=None
        ):
            window.main()
        arguments = launch.call_args.args[0]
        self.assertIn("--disable-backgrounding-occluded-windows", arguments)
        disabled_features = next(arg for arg in arguments if arg.startswith("--disable-features=")).split("=", 1)[1].split(",")
        self.assertIn("CalculateNativeWinOcclusion", disabled_features)
        self.assertIn("ApplyNativeOcclusionToCompositor", disabled_features)
        self.assertNotIn("--disable-gpu", arguments)
        self.assertNotIn("--disable-background-timer-throttling", arguments)

    def test_identity_guard_does_not_reconfigure_the_frame(self):
        api = MagicMock()
        with patch.object(window, "_user32", api), patch.object(
            window, "_get_window_long_ptr", return_value=0
        ), patch.object(window, "_set_window_long_ptr") as set_style, patch.object(
            window, "_taskbar_icon", 123
        ):
            api.SendMessageW.return_value = 123
            window._hide_caption_icon(1)
            set_style.assert_not_called()
            api.SetWindowPos.assert_not_called()
            api.SetForegroundWindow.assert_not_called()

    def test_initial_frame_configuration_preserves_focus_and_z_order(self):
        api = MagicMock()
        with patch.object(window, "_user32", api), patch.object(
            window, "_get_window_long_ptr", return_value=0
        ), patch.object(window, "_set_window_long_ptr") as set_style, patch.object(
            window, "_taskbar_icon", 123
        ):
            api.SendMessageW.return_value = 123
            window._hide_caption_icon(1, configure_frame=True)
            set_style.assert_called_once()
            flags = api.SetWindowPos.call_args.args[-1]
            self.assertTrue(flags & window._SWP_NOZORDER)
            self.assertTrue(flags & window._SWP_NOACTIVATE)
            self.assertTrue(flags & window._SWP_NOSIZE)
            self.assertTrue(flags & window._SWP_NOMOVE)

    def test_blank_or_invisible_caption_does_not_trigger_a_repaint(self):
        for title in ("", window._WINDOW_READY_TITLE):
            with self.subTest(title=title), patch.object(
                window, "_window_title", return_value=title
            ), patch.object(window, "_user32") as api:
                window._clear_caption_text(1)
                api.SetWindowTextW.assert_not_called()

    def test_visible_browser_caption_is_still_hidden(self):
        with patch.object(window, "_window_title", return_value="NeveAI"), patch.object(
            window, "_user32"
        ) as api:
            window._clear_caption_text(1)
            api.SetWindowTextW.assert_called_once_with(1, "")

    def test_taskbar_icon_is_restored_without_changing_geometry(self):
        api = MagicMock()
        with patch.object(window, "_user32", api), patch.object(
            window, "_get_window_long_ptr", return_value=0
        ), patch.object(window, "_taskbar_icon", 123):
            api.SendMessageW.return_value = 0
            window._hide_caption_icon(1)
            replacements = [
                call for call in api.SendMessageW.call_args_list
                if call.args[1] == window._WM_SETICON
            ]
            self.assertEqual(len(replacements), 2)
            self.assertEqual({call.args[2] for call in replacements}, {window._ICON_BIG, window._ICON_SMALL})
            api.SetWindowPos.assert_not_called()


if __name__ == "__main__":
    unittest.main()
