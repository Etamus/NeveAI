"""Isolated source-update and sharded music-readiness regressions."""
import ast
import asyncio
import importlib.util
import io
import json
import os
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from typing import Optional
import zipfile
from pathlib import Path
from unittest.mock import patch
from unittest.mock import AsyncMock

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("comfy_runtime", ROOT / "backend/neveai/utils/comfy_runtime.py")
comfy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(comfy)


def archive(entries):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as package:
        for name, value in entries.items():
            package.writestr(name, value)
    stream.seek(0)
    return stream


class SourceUpdateTests(unittest.TestCase):
    def test_update_preserves_data_and_previous_source(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "ComfyUI"
            target.mkdir()
            (target / "main.py").write_text("old")
            (target / "models").mkdir()
            (target / "models/weights").write_bytes(b"untouched")
            with patch.object(comfy.urllib.request, "urlopen", return_value=archive({"source/main.py": "new", "source/requirements.txt": "", "source/models/example": "placeholder"})):
                comfy.install_comfy_source(target)
            self.assertEqual((target / "main.py").read_text(), "new")
            self.assertEqual((target / "models/weights").read_bytes(), b"untouched")
            self.assertEqual(next(Path(directory).glob("ComfyUI.previous-*/main.py")).read_text(), "old")
            with patch.object(comfy.urllib.request, "urlopen", side_effect=AssertionError("must not download twice")):
                comfy.install_comfy_source(target)

    def test_unsafe_or_incomplete_archive_does_not_touch_previous(self):
        for entries in ({"../escape": "x"}, {"source/main.py": "new"}):
            with self.subTest(entries=entries), tempfile.TemporaryDirectory() as directory:
                target = Path(directory) / "ComfyUI"
                target.mkdir()
                (target / "main.py").write_text("old")
                with patch.object(comfy.urllib.request, "urlopen", return_value=archive(entries)):
                    with self.assertRaises(RuntimeError):
                        comfy.install_comfy_source(target)
                self.assertEqual((target / "main.py").read_text(), "old")

    def test_publish_failure_rolls_back_source_and_models(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "ComfyUI"
            target.mkdir()
            (target / "main.py").write_text("old")
            (target / "models").mkdir()
            (target / "models/weights").write_bytes(b"original")
            rename = Path.rename
            def fail_publish(path, destination):
                if path.name == "source" and destination == target.resolve():
                    raise OSError("publish failed")
                return rename(path, destination)
            # Archive root and staging extraction directory deliberately differ.
            with patch.object(comfy.urllib.request, "urlopen", return_value=archive({"source/main.py": "new", "source/requirements.txt": ""})), patch.object(Path, "rename", fail_publish):
                with self.assertRaises(OSError):
                    comfy.install_comfy_source(target)
            self.assertEqual((target / "main.py").read_text(), "old")
            self.assertEqual((target / "models/weights").read_bytes(), b"original")


class ImageContractTests(unittest.TestCase):
    def test_image_workflow_and_reference_policy_are_unchanged(self):
        name = "backend/neveai/routers/image_fast_generation.py"
        before = ast.parse(subprocess.check_output(["git", "show", "HEAD:" + name], cwd=ROOT, text=True, encoding="utf-8"))
        after = ast.parse((ROOT / name).read_text(encoding="utf-8"))
        def functions(tree):
            return {node.name: ast.dump(node) for node in ast.walk(tree)
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
        old, new = functions(before), functions(after)
        for function in ("build_workflow", "_reference_size", "_encode_reference_png", "_run_once"):
            self.assertEqual(old[function], new[function], function)


class MusicReadinessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        tree = ast.parse((ROOT / "backend/neveai/routers/music_generation.py").read_text(encoding="utf-8"))
        runtime = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "AceStepRuntime")
        method = next(node for node in runtime.body if isinstance(node, ast.FunctionDef) and node.name == "_has_model_weights")
        method.decorator_list = []
        namespace = dict(Path=Path, json=json)
        exec(compile(ast.Module(body=[method], type_ignores=[]), "readiness", "exec"), namespace)
        cls.ready = staticmethod(namespace["_has_model_weights"])

    def test_sharded_weights_require_all_shards(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "model.safetensors.index.json").write_text(json.dumps({"weight_map": {"a": "part1", "b": "part2"}}))
            self.assertFalse(self.ready(root))
            (root / "part1").write_bytes(b"one")
            self.assertFalse(self.ready(root))
            (root / "part2").write_bytes(b"two")
            self.assertTrue(self.ready(root))


    def test_simple_and_invalid_indexes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "model.safetensors.index.json").write_text("{")
            self.assertFalse(self.ready(root))
            (root / "model.safetensors").write_bytes(b"valid")
            self.assertTrue(self.ready(root))


class MusicDownloadTests(unittest.IsolatedAsyncioTestCase):
    async def test_only_missing_components_download_and_xl_is_pinned(self):
        tree = ast.parse((ROOT / "backend/neveai/routers/music_generation.py").read_text(encoding="utf-8"))
        runtime = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "AceStepRuntime")
        wanted = {"_has_model_weights", "_generation_component_ready", "_ensure_generation_models", "_directory_size", "_format_size"}
        runtime.body = [node for node in runtime.body if getattr(node, "name", None) in wanted]
        namespace = dict(Path=Path, json=json, os=os, asyncio=asyncio, Optional=Optional, ProgressCallback=object,
                         _runtime_python=lambda: Path("python.exe"))
        for node in tree.body:
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id in {"ACE_STEP_MODEL", "ACE_STEP_MODEL_REPO", "ACE_STEP_MODEL_REVISION", "ACE_STEP_MAIN_REPO", "ACE_STEP_BOOTSTRAP_COMPONENTS"}:
                        namespace[target.id] = ast.literal_eval(node.value)
        exec(compile(ast.Module(body=[runtime], type_ignores=[]), "download", "exec"), namespace)
        with tempfile.TemporaryDirectory() as directory:
            namespace["ACE_STEP_SOURCE_DIR"] = Path(directory)
            instance = namespace["AceStepRuntime"]()
            def ready(name):
                path = Path(directory) / "checkpoints" / name
                path.mkdir(parents=True, exist_ok=True)
                (path / "config.json").write_text("{}")
                (path / "model.safetensors").write_bytes(b"weights")
            for name in ("Qwen3-Embedding-0.6B", "vae", *namespace["ACE_STEP_BOOTSTRAP_COMPONENTS"]):
                ready(name)
            async def download(command):
                ready(namespace["ACE_STEP_MODEL"])
            instance._run_setup_command = AsyncMock(side_effect=download)
            await instance._ensure_generation_models(AsyncMock(), lm_model="acestep-5Hz-lm-1.7B")
            script = instance._run_setup_command.call_args.args[0][-1]
            self.assertIn(namespace["ACE_STEP_MODEL_REVISION"], script)
            self.assertIn(namespace["ACE_STEP_MODEL_REPO"], script)
            self.assertNotIn(namespace["ACE_STEP_MAIN_REPO"], script)
            instance._run_setup_command.reset_mock()
            await instance._ensure_generation_models(AsyncMock())
            instance._run_setup_command.assert_not_awaited()


class ModeCompatibilityTests(unittest.IsolatedAsyncioTestCase):
    async def test_vbar_retry_preserves_arguments_and_is_bounded(self):
        class ImageGenerationError(RuntimeError):
            pass
        for faults in (1, 2):
            calls = []
            class Base:
                def __init__(self):
                    pass
                def _comfy_command(self):
                    return ["comfy"]
                async def _run_once(self, *args, **kwargs):
                    calls.append((self._comfy_command(), args, kwargs))
                    if len(calls) <= faults:
                        raise ImageGenerationError("Neve Image 2 falhou: RuntimeError: Fault failed: 2")
                    return "image"
            source = ast.parse((ROOT / "backend/neveai/routers/image_fast_modes.py").read_text(encoding="utf-8"))
            runtime = next(node for node in source.body if isinstance(node, ast.ClassDef) and node.name == "NeveImage2ModeRuntime")
            runtime.body = [node for node in runtime.body if getattr(node, "name", None) in {"__init__", "_run_once", "_comfy_command"}]
            namespace = dict(ImageModeOptions=object, _VERIFIED_MODE_ASSETS={}, ImageGenerationError=ImageGenerationError,
                             fast=SimpleNamespace(NeveImage2SRuntime=Base, log=SimpleNamespace(warning=lambda *args: None)))
            exec(compile(ast.Module(body=[runtime], type_ignores=[]), "mode", "exec"), namespace)
            instance = namespace["NeveImage2ModeRuntime"](object())
            if faults == 1:
                self.assertEqual(await instance._run_once("prompt", seed=42), "image")
            else:
                with self.assertRaises(ImageGenerationError):
                    await instance._run_once("prompt", seed=42)
            self.assertEqual(len(calls), 2)
            self.assertNotIn("--disable-dynamic-vram", calls[0][0])
            self.assertIn("--disable-dynamic-vram", calls[1][0])
            self.assertEqual(calls[0][1:], calls[1][1:])
            self.assertFalse(instance._legacy_memory)

if __name__ == "__main__":
    unittest.main()
