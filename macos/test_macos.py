import ast
import importlib.util
import io
import json
import os
import sys
import tarfile
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import adapt
import manage
from package_launchers import package


class MacIsolationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.here = Path(self.temp.name) / "macos"
        self.here.mkdir()
        self.patcher = patch.multiple(
            manage,
            HERE=self.here,
            RUNTIME=self.here / ".runtime",
            APP=self.here / ".runtime/app",
        )
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

    def test_outside_write_rejected(self):
        with self.assertRaises(ValueError):
            manage.checked_path(self.here.parent / "Windows/.env")
        with self.assertRaises(ValueError):
            manage.checked_path(self.here)

    def test_json_written_only_inside(self):
        target = self.here / ".runtime/installation.json"
        manage.write_json(target, {"arch": "arm64"})
        self.assertEqual(json.loads(target.read_text()), {"arch": "arm64"})
        self.assertFalse(target.with_suffix(".tmp").exists())

    def test_host_must_be_mac(self):
        with patch.object(manage.sys, "platform", "win32"):
            with self.assertRaisesRegex(RuntimeError, "Exclusivo"):
                manage.native_arch()

    def test_windows_data_is_not_used(self):
        env = manage.environment()
        self.assertTrue(env["DATA_DIR"].startswith(str(self.here)))
        self.assertEqual(env["USE_CUDA_DOCKER"], "false")
        self.assertEqual(env["ENABLE_VIDEO_GENERATION"], "false")
        self.assertEqual(env["PYTORCH_ENABLE_MPS_FALLBACK"], "1")
        self.assertTrue(
            env["DATABASE_URL"].startswith(
                "sqlite:///" + str(self.here).replace("\\", "/")
            )
        )
        self.assertTrue(env["npm_config_cache"].startswith(str(self.here)))
        self.assertTrue(env["PIP_CACHE_DIR"].startswith(str(self.here)))

    def test_archive_traversal_rejected(self):
        archive = self.here / "bad.zip"
        with zipfile.ZipFile(archive, "w") as output:
            output.writestr("../../Windows/.env", "bad")
        with self.assertRaises(ValueError):
            manage.unpack(archive, self.here / "stage")

    def test_tar_external_link_rejected(self):
        archive = self.here / "bad.tar.gz"
        with tarfile.open(archive, "w:gz") as output:
            link = tarfile.TarInfo("lib/native.dylib")
            link.type = tarfile.SYMTYPE
            link.linkname = "../../../outside"
            output.addfile(link)
        with self.assertRaises(ValueError):
            manage.unpack(archive, self.here / "stage")

    def test_valid_archive_extracted(self):
        archive = self.here / "good.zip"
        with zipfile.ZipFile(archive, "w") as output:
            output.writestr("bin/llama-server", "native")
        manage.unpack(archive, self.here / "stage")
        self.assertEqual((self.here / "stage/bin/llama-server").read_text(), "native")

    def test_download_checksum_failure_does_not_replace_file(self):
        destination = self.here / "binary"
        destination.write_bytes(b"existing")
        with patch.object(
            manage.urllib.request, "urlopen", return_value=io.BytesIO(b"bad")
        ):
            with self.assertRaisesRegex(RuntimeError, "Checksum"):
                manage.download("https://example.com/binary", destination, "0" * 64)
        self.assertEqual(destination.read_bytes(), b"existing")
        self.assertFalse(destination.with_suffix(".part").exists())

    def test_dotenv_and_windows_environments_not_in_snapshot_allowlist(self):
        tree = ast.parse(Path(manage.__file__).read_text())
        function = next(
            node
            for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == "snapshot"
        )
        copied_names = [
            value.value
            for node in ast.walk(function)
            if isinstance(node, ast.For) and isinstance(node.iter, ast.Tuple)
            for value in node.iter.elts
            if isinstance(value, ast.Constant)
        ]
        self.assertNotIn(".env", copied_names)
        self.assertNotIn("node_modules", copied_names)
        self.assertNotIn("neve_window.py", copied_names)

    def test_core_native_dependencies_are_architecture_specific(self):
        runtime = self.here / ".runtime"
        runtime.mkdir()
        with patch.object(manage, "SOURCE", Path(__file__).resolve().parents[1]):
            apple = manage.requirements("arm64").read_text()
            self.assertIn("torch==2.11.0", apple)
            self.assertIn("pypandoc-binary==1.17", apple)
            self.assertNotIn("pypandoc==", apple)
            intel = manage.requirements("x86_64").read_text()
            self.assertIn("torch==2.2.2", intel)
            self.assertIn("transformers==4.46.3", intel)

    def test_source_contracts_and_mac_adaptation(self):
        source = Path(__file__).resolve().parents[1] / "backend/neveai"
        target = self.here / ".runtime/app/backend/neveai"
        (target / "routers").mkdir(parents=True)
        names = [
            "main.py",
            "routers/llamacpp.py",
            "routers/image_fast_generation.py",
            "routers/image_quality_generation.py",
        ]
        hashes = {name: (source / name).read_bytes() for name in names}
        for name in names:
            (target / name).write_bytes(hashes[name])
        component = target.parents[1] / "src/lib/components/chat/UnifiedModels.svelte"
        component.parent.mkdir(parents=True)
        original_component = (
            source.parents[1] / "src/lib/components/chat/UnifiedModels.svelte"
        )
        component.write_bytes(original_component.read_bytes())
        adapt.adapt_snapshot(target.parents[1])
        fast = ast.parse((target / "routers/image_fast_generation.py").read_text())
        text = ast.unparse(fast)
        self.assertNotIn("https://download.pytorch.org/whl/cu130", text)
        self.assertIn("torch.backends.mps.is_available()", text)
        self.assertIn("https://pypi.org/simple", text)
        main = (target / "main.py").read_text()
        self.assertIn("'/usr/bin/open'", main)
        self.assertIn("bin-macos-", main)
        for name in names:
            self.assertEqual((source / name).read_bytes(), hashes[name])

    def test_uv_python_and_scripts_parse(self):
        root = Path(__file__).resolve().parent
        for path in root.glob("*.py"):
            ast.parse(path.read_text(encoding="utf-8"))
        text = (root / "bootstrap.sh").read_text()
        self.assertIn('UV_PYTHON_INSTALL_DIR="$HERE/.runtime/python"', text)
        self.assertNotIn("sudo ", text)
        self.assertIn("shasum -a 256", text)

    def test_packaged_launchers_have_executable_bits(self):
        target = package(self.here / "launchers.zip")
        with zipfile.ZipFile(target) as archive:
            names = archive.namelist()
            self.assertFalse(any("/.runtime/" in name for name in names))
            for name in names:
                if name.endswith((".command", ".sh", "/NeveLaunch")):
                    self.assertEqual(
                        archive.getinfo(name).external_attr >> 16 & 0o777, 0o755
                    )


if __name__ == "__main__":
    unittest.main()
