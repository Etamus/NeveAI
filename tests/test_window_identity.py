"""Desktop launcher/install contracts; no production profile changes."""
import asyncio
import ast
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from unittest.mock import Mock
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import neve_window as window
from desktop import setup_runtime as setup
from desktop import profile_migration as migration


class FixedRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="neve desktop test ")
        self.store = Path(self.temporary.name) / ".desktop"
        self.store.mkdir()
        self.patch = patch.object(setup, "STORE", self.store)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.addCleanup(self.temporary.cleanup)
        self.config = {"runtime_version": "156.0.4314.42"}
        self.host = self.store / "host"
        self.host.mkdir()
        self.runtime = self.store / "runtime"
        self.runtime.mkdir()
        for name in ("NeveAI.Window.exe", "Microsoft.Web.WebView2.Core.dll", "Microsoft.Web.WebView2.WinForms.dll", "WebView2Loader.dll"):
            (self.host / name).write_bytes(b"test")
        for name in ("msedgewebview2.exe", "msedge.dll", "icudtl.dat", "resources.pak"):
            (self.runtime / name).write_bytes(b"runtime")
        self.state = {"host": "host/NeveAI.Window.exe", "runtime": "runtime", "runtime_version": self.config["runtime_version"],
                      "source_key": "test", "files": {str(file.relative_to(self.store)).replace("\\", "/"): setup.sha256(file) for file in self.host.iterdir()},
                      "runtime_files": {file.name: {"size": file.stat().st_size, "sha256": setup.sha256(file)} for file in self.runtime.iterdir()}}
        self.save()
        key = patch.object(setup, "source_key", return_value="test")
        key.start()
        self.addCleanup(key.stop)

    def save(self):
        (self.store / "installed.json").write_text(json.dumps(self.state))

    def test_valid_install_fast_and_full(self):
        self.assertTrue(setup.validate(self.config))
        self.assertTrue(setup.validate(self.config, full=True))

    def test_missing_runtime_resource_fails(self):
        (self.runtime / "resources.pak").unlink()
        self.assertFalse(setup.validate(self.config))

    def test_corrupt_host_fails(self):
        (self.host / "NeveAI.Window.exe").write_bytes(b"changed")
        self.assertFalse(setup.validate(self.config))

    def test_full_runtime_verification_detects_same_size_corruption(self):
        (self.runtime / "msedge.dll").write_bytes(b"changed")
        self.assertFalse(setup.validate(self.config, full=True))

    def test_stale_manifest_or_source_fails(self):
        self.state["source_key"] = "old"
        self.save()
        self.assertFalse(setup.validate(self.config))

    def test_incomplete_host_catalog_fails(self):
        self.state["files"] = {}
        self.save()
        self.assertFalse(setup.validate(self.config))

    def test_path_escape_fails(self):
        self.state["host"] = "../outside.exe"
        self.save()
        self.assertFalse(setup.validate(self.config))
        with self.assertRaises(ValueError):
            setup.inside_store(self.store)

    def test_download_hash_is_checked_before_publish(self):
        destination = self.store / "download.zip"
        payload = b"verified archive"
        with patch.object(setup.urllib.request, "urlopen", return_value=io.BytesIO(payload)):
            setup.download("https://example.test", destination, hashlib.sha256(payload).hexdigest())
        self.assertEqual(destination.read_bytes(), payload)
        destination.unlink()
        with patch.object(setup.urllib.request, "urlopen", return_value=io.BytesIO(payload)):
            with self.assertRaisesRegex(RuntimeError, "integridade"):
                setup.download("https://example.test", destination, "0" * 64)
        self.assertFalse(destination.exists())


class LauncherTests(unittest.TestCase):
    def test_launcher_never_falls_back_to_browser_or_evergreen(self):
        with patch.object(window, "validate", return_value=False), patch.object(window, "migrate") as migrate, patch.object(window.subprocess, "call") as call:
            with self.assertRaisesRegex(RuntimeError, "instalar.bat"):
                window.launch()
            migrate.assert_not_called()
            call.assert_not_called()

    def test_launch_pins_host_runtime_profile_and_preserves_ready_signal(self):
        config = json.loads(setup.MANIFEST.read_text())
        state = {"host": "host/NeveAI.Window.exe", "runtime": "runtime"}
        real_read = Path.read_text
        def read(path, *args, **kwargs):
            return json.dumps(state) if path.name == "installed.json" else real_read(path, *args, **kwargs)
        with patch.object(window, "validate", return_value=True), patch.object(window, "migrate") as migrate, patch.object(Path, "read_text", read), patch.object(window.subprocess, "call", return_value=0) as call, patch.dict(os.environ, {
            "NEVE_WINDOW_READY_FILE": str(ROOT / "logs/test ready.tmp"), "WEBVIEW2_BROWSER_EXECUTABLE_FOLDER": "wrong", "WEBVIEW2_USER_DATA_FOLDER": "wrong", "WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS": "--disable-gpu"
        }):
            self.assertEqual(window.launch(), 0)
        migrate.assert_called_once_with(ROOT)
        args = call.call_args.args[0]
        self.assertIn("--runtime", args)
        self.assertIn("--profile", args)
        self.assertIn("--ready-file", args)
        self.assertFalse(any("--app=" in arg for arg in args))
        env = call.call_args.kwargs["env"]
        self.assertNotIn("WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS", env)
        self.assertEqual(env["WEBVIEW2_DEFAULT_BACKGROUND_COLOR"], "FF000000")

    def test_installer_and_update_prepare_runtime_and_preserve_generated_folder(self):
        source = (ROOT / "launchers/instalar.ps1").read_text(encoding="utf-8-sig")
        self.assertIn("Run $VENV_PY @($desktopSetup)", source)
        self.assertIn("Run $desktopPython @($desktopSetup)", source)
        self.assertIn("'.desktop'", source)
        self.assertIn("$desktopStateBackup = Join-Path $rollbackRoot '.desktop\\installed.json'", source)
        self.assertIn("/.desktop/", (ROOT / ".gitignore").read_text(encoding="utf-8"))

    def test_native_host_keeps_rendering_and_does_not_use_focus_polling(self):
        source = (ROOT / "desktop/NeveWindow.cs").read_text()
        self.assertIn("--disable-backgrounding-occluded-windows", source)
        self.assertNotIn("--disable-gpu", source)
        self.assertNotIn("Thread.Sleep", source)
        self.assertIn("core.NewWindowRequested += OpenPopup", source)
        self.assertIn("e.NewWindow = preview.CoreWebView2", source)
        self.assertIn('"neve:ready"', source)

    def test_initial_and_duplicate_windows_explicitly_restore_and_raise_once(self):
        source = (ROOT / "desktop/NeveWindow.cs").read_text()
        self.assertIn("PresentWindow(Handle)", source)
        self.assertIn("PresentWindow(existing)", source)
        self.assertIn("IsIconic(hwnd) ? 9 : 5", source)
        self.assertIn("SetWindowPos(hwnd, IntPtr.Zero", source)
        self.assertNotIn("TopMost = true", source)


class MigrationTests(unittest.TestCase):
    def test_fresh_install_does_not_start_a_browser(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(migration.subprocess, "Popen") as launch:
            asyncio.run(migration.export_legacy_storage(Path(directory)))
            launch.assert_not_called()

    def test_completed_migration_is_not_repeated(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(migration.subprocess, "Popen") as launch:
            root = Path(directory)
            folder = root / "logs/webview2"
            folder.mkdir(parents=True)
            (folder / "migration-complete").write_text("complete")
            asyncio.run(migration.export_legacy_storage(root))
            launch.assert_not_called()


class ShutdownTests(unittest.TestCase):
    def test_shutdown_closes_only_this_projects_webview_processes(self):
        main = ROOT / "backend/neveai/main.py"
        tree = ast.parse(main.read_text(encoding="utf-8"))
        handler = next(node for node in tree.body if isinstance(node, ast.AsyncFunctionDef) and node.name == "shutdown_app")
        handler.decorator_list = []
        scope = {"__file__": str(main), "Path": Path, "os": SimpleNamespace(kill=Mock(), getpid=lambda: 999, sep=os.sep), "BackgroundTasks": object,
                 "Depends": lambda function: None, "get_admin_user": lambda: None}
        exec(compile(ast.Module(body=[handler], type_ignores=[]), str(main), "exec"), scope)
        own = Mock(info={"name": "NeveAI.Window.exe"})
        own.cmdline.return_value = [str(ROOT / ".desktop/host/NeveAI.Window.exe")]
        other = Mock(info={"name": "msedgewebview2.exe"})
        other.cmdline.return_value = [r"C:\OtherApp\msedgewebview2.exe"]
        tasks = Mock()
        asyncio.run(scope["shutdown_app"](tasks, None))
        import psutil
        with patch.object(psutil, "process_iter", return_value=[own, other]), patch("time.sleep"):
            tasks.add_task.call_args.args[0]()
        own.kill.assert_called_once()
        other.kill.assert_not_called()
        scope["os"].kill.assert_called_once()

if __name__ == "__main__":
    unittest.main()
