"""Native audio wiring and shared model preparation, without loading the app/DB."""
import ast
import asyncio
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import AsyncMock, patch

from test_video_vdn_generation import VIDEO, execute, vdn_namespace


class NativeVideoAudioTests(unittest.IsolatedAsyncioTestCase):
    def test_loading_audio_weights_cannot_jump_progress_ahead_of_sampling(self):
        tree = ast.parse(VIDEO.read_text(encoding="utf8"))
        bounds = next(n for n in ast.walk(tree) if isinstance(n, ast.Assign)
                      and any(isinstance(t, ast.Name) and t.id == "node_progress_bounds" for t in n.targets))
        phases = ast.literal_eval(bounds.value)
        # A dependency-free loader can run before denoising; it is not a completion phase.
        self.assertNotIn("17", phases)
        self.assertEqual(phases["18"], phases["14"])
        self.assertGreaterEqual(phases["18"][0], phases["12"][1])

    async def test_audio_vae_is_required_once_and_shared_by_both_runtimes(self):
        with tempfile.TemporaryDirectory() as directory:
            ns = vdn_namespace(Path(directory))
            original = ns["h3"].MiniMaxH3Runtime()
            vdn = ns["vdn_h3_runtime"]
            paths = original._model_paths()
            audio = ns["h3"].COMFYUI_MODELS / "vae" / ns["h3"].AUDIO_VAE
            self.assertEqual(paths, vdn._model_paths())
            self.assertEqual(len(paths), len(set(paths)))
            self.assertEqual(paths.count(audio), 1)
            for path in paths:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b"x" * 1025)
            self.assertTrue(original.models_ready)
            audio.unlink()
            self.assertFalse(original.models_ready)
            audio.write_bytes(b"partial")
            self.assertFalse(original.models_ready)
            audio.write_bytes(b"x" * 1025)
            self.assertTrue(original.models_ready)

    async def test_preparation_downloads_audio_with_the_existing_model_pipeline(self):
        with tempfile.TemporaryDirectory() as directory:
            ns = vdn_namespace(Path(directory))
            scope = vars(ns["h3"]).copy()
            scope["os"] = os
            scope["VIDEO_HF_CACHE"] = Path(directory) / "huggingface"
            scope["_runtime_python"] = lambda: Path(sys.executable)
            runtime_node = next(n for n in ast.parse(VIDEO.read_text(encoding="utf8")).body
                                if isinstance(n, ast.ClassDef) and n.name == "MiniMaxH3Runtime")
            methods = [n for n in runtime_node.body if getattr(n, "name", None) in {
                "ensure_models", "_format_size", "_directory_size"}]
            for method in methods:
                method.decorator_list = []
            execute(methods, scope)
            runtime = scope["MiniMaxH3Runtime"]()
            runtime._directory_size = scope["_directory_size"]
            runtime._format_size = scope["_format_size"]
            downloads = []

            def download(repo_id, filename, local_dir):
                downloads.append((repo_id, filename, local_dir))
                path = Path(local_dir) / filename
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b"x" * 1025)

            async def command(arguments):
                module = types.ModuleType("huggingface_hub")
                module.hf_hub_download = download
                with patch.dict(sys.modules, {"huggingface_hub": module}):
                    exec(arguments[-1], {})

            runtime._run_command = AsyncMock(side_effect=command)
            # Avoid a real download-monitor sleep without patching asyncio globally.
            async def yield_once(_):
                await asyncio.sleep(0)

            scope["asyncio"] = types.SimpleNamespace(
                to_thread=asyncio.to_thread, create_task=asyncio.create_task,
                sleep=yield_once, CancelledError=asyncio.CancelledError)
            progress = AsyncMock()
            await scope["ensure_models"](runtime, progress)
            audio_downloads = [item for item in downloads if "audio_vae" in item[1]]
            self.assertEqual(audio_downloads, [(
                "Comfy-Org/MiniMax-H3", "vae/" + scope["AUDIO_VAE"],
                str(scope["COMFYUI_MODELS"]),
            )])
            self.assertTrue(runtime.models_ready)
            runtime._run_command.reset_mock()
            await scope["ensure_models"](runtime, progress)
            runtime._run_command.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
