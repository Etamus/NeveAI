"""CPU-only regressions; execute production AST without importing the app/DB."""
import ast
import asyncio
from collections import deque
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock
from uuid import uuid4
from neveai.utils.media_standby import media_model_standby


ROOT = Path(__file__).resolve().parents[1]
VIDEO = ROOT / "backend/neveai/routers/video_generation.py"
VDN = ROOT / "backend/neveai/routers/video_vdn_generation.py"
MIDDLEWARE = ROOT / "backend/neveai/utils/middleware.py"


def execute(nodes, namespace):
    future = ast.ImportFrom(
        module="__future__", names=[ast.alias(name="annotations")], level=0
    )
    module = ast.fix_missing_locations(ast.Module(body=[future, *nodes], type_ignores=[]))
    exec(compile(module, "extracted-video-code", "exec"), namespace)


class WithoutImports(ast.NodeTransformer):
    def visit_Import(self, node):
        return None

    def visit_ImportFrom(self, node):
        return None


def extracted_function(path, name, namespace):
    node = next(n for n in ast.parse(path.read_text(encoding="utf8")).body
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name)
    node.decorator_list = []
    execute([WithoutImports().visit(node)], namespace)
    return namespace[name]


def base_namespace(source=None):
    tree = ast.parse(source if source is not None else VIDEO.read_text(encoding="utf8"))
    namespace = dict(asyncio=asyncio, deque=deque, Path=Path)
    for node in tree.body:
        if isinstance(node, ast.Assign):
            try:
                value = ast.literal_eval(node.value)
            except (ValueError, TypeError):
                continue
            for target in node.targets:
                if isinstance(target, ast.Name):
                    namespace[target.id] = value
    runtime = next(n for n in tree.body if isinstance(n, ast.ClassDef)
                   and n.name == "MiniMaxH3Runtime")
    retained = {"__init__", "_build_workflow", "_worker_paths", "_worker_extra_arguments",
                "cancel", "stop", "models_ready", "_model_paths", "is_running"}
    runtime.body = [n for n in runtime.body if getattr(n, "name", None) in retained]
    align = next(n for n in tree.body if isinstance(n, ast.FunctionDef)
                 and n.name == "_align_video_dimension")
    execute([align, runtime], namespace)
    return namespace


def vdn_namespace(cache):
    base = base_namespace()
    shared = cache / "video_generation"
    for name, suffix in {
        "VIDEO_ROOT": "", "COMFYUI_INPUT": "input", "COMFYUI_OUTPUT": "output",
        "COMFYUI_TEMP": "temp", "VIDEO_HF_CACHE": "huggingface",
        "COMFYUI_CUSTOM_NODES": "custom_nodes", "COMFYUI_MODELS": "models",
    }.items():
        base[name] = shared / suffix
    h3 = SimpleNamespace(**base)
    h3.minimax_h3_runtime = SimpleNamespace(prepare=AsyncMock(), is_installed=True)
    h3._runtime_python = lambda: cache / "python"
    h3._replace_source_from_archive = Mock()
    namespace = dict(CACHE_DIR=cache, h3=h3, asyncio=asyncio, json=json, shutil=shutil, Path=Path)
    nodes = [n for n in ast.parse(VDN.read_text(encoding="utf8")).body
             if not isinstance(n, (ast.Import, ast.ImportFrom))]
    execute(nodes, namespace)
    return namespace


class VideoVDNGraphTests(unittest.TestCase):
    def setUp(self):
        self.ns = vdn_namespace(Path("test-cache"))
        self.base = self.ns["h3"].MiniMaxH3Runtime
        self.vdn = self.ns["VDNH3Runtime"]

    def test_original_graph_matches_head_for_all_reference_modes(self):
        old_source = subprocess.check_output(
            ["git", "show", "HEAD:backend/neveai/routers/video_generation.py"],
            cwd=ROOT, text=True, encoding="utf8",
        )
        original = base_namespace(old_source)["MiniMaxH3Runtime"]
        for refs in [(None, None), ("first.png", None), ("first.png", "last.png")]:
            for frames in (124, 196):
                for merged in (False, True):
                    with self.subTest(refs=refs, frames=frames, merged=merged):
                        args = ("Scene", 42, *refs, 864, 480, frames, merged)
                        self.assertEqual(original._build_workflow(*args), self.base._build_workflow(*args))

    def test_vdn_changes_only_own_adapters_and_beta8_er_sde(self):
        for count in range(3):
            for frames in (124, 196):
                for merged in (False, True):
                    with self.subTest(references=count, frames=frames, merged=merged):
                        refs = ("first.png" if count else None, "last.png" if count == 2 else None)
                        args = ("Scene", 42, *refs, 864, 480, frames, merged)
                        baseline = self.base._build_workflow(*args)
                        graph = self.vdn._build_workflow(*args)
                        self.assertEqual(set(graph), set(baseline))
                        self.assertEqual({k for k in graph if graph[k] != baseline[k]}, {"7", "9", "11"})
                        adapter = graph["7"]
                        self.assertEqual(adapter["class_type"], "ApplyVDNH3")
                        self.assertEqual(adapter["inputs"]["model"], ["6", 0])
                        self.assertEqual(adapter["inputs"]["vdn_checkpoint"], self.ns["STAGE"])
                        self.assertIs(adapter["inputs"]["apply_turbo_adapter"], True)
                        self.assertEqual(adapter["inputs"]["lora_mode"], "merge")
                        self.assertEqual(adapter["inputs"]["strength"], 1.0)
                        self.assertNotIn("MiniMaxH3TurboLoRA", [n["class_type"] for n in graph.values()])
                        self.assertNotIn(self.ns["h3"].TURBO_LORA, json.dumps(graph))
                        self.assertEqual(graph["9"]["inputs"]["scheduler"], "beta")
                        self.assertEqual(graph["9"]["inputs"]["steps"], 8)
                        self.assertEqual(graph["11"], {"class_type": "KSamplerSelect", "inputs": {"sampler_name": "er_sde"}})
                        conditioning = graph["4"]["inputs"]
                        self.assertEqual(conditioning["length"], frames)
                        self.assertEqual((conditioning["width"], conditioning["height"]), (864, 480))
                        for key, node_id, image, present in (
                            ("first_frame", "20", refs[0], count > 0),
                            ("last_frame", "21", refs[1], count == 2),
                        ):
                            self.assertEqual(key in conditioning, present)
                            self.assertEqual(node_id in graph, present)
                            if present:
                                self.assertEqual(conditioning[key], [node_id, 0])
                                self.assertEqual(graph[node_id]["inputs"]["image"], image)
                        self.assertEqual(graph["8"]["inputs"]["model"], ["7", 0])
                        self.assertEqual(graph["9"]["inputs"]["model"], ["7", 0])

    def test_worker_paths_and_extra_arguments_are_isolated(self):
        original = self.base()
        vdn = self.vdn()
        self.assertEqual(original._worker_extra_arguments(), [])
        self.assertTrue(set(original._worker_paths()).isdisjoint(vdn._worker_paths()))
        self.assertEqual(vdn._worker_paths(), tuple(self.ns["ROOT"] / p for p in ("", "input", "output", "temp", "huggingface")))
        self.assertEqual(vdn._worker_extra_arguments(), [
            "--extra-model-paths-config", str(self.ns["ROOT"] / "shared_paths.yaml"),
            "--disable-comfy-compiler",
        ])


class VideoVDNPreparationTests(unittest.IsolatedAsyncioTestCase):
    async def test_models_ready_requires_shared_base_and_every_vdn_file(self):
        with tempfile.TemporaryDirectory() as directory:
            ns = vdn_namespace(Path(directory))
            runtime = ns["vdn_h3_runtime"]
            base_files = runtime._model_paths()
            vdn_files = tuple(ns["STAGE_DIR"] / name for name in ns["MODEL_FILES"])
            self.assertFalse(runtime.models_ready)
            for path in base_files:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b"x" * 1025)
            self.assertFalse(runtime.models_ready)
            for path in vdn_files:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b"downloaded")
            self.assertTrue(runtime.models_ready)
            for path in (*base_files, *vdn_files):
                with self.subTest(missing=path.relative_to(directory)):
                    content = path.read_bytes()
                    path.unlink()
                    self.assertFalse(runtime.models_ready)
                    path.write_bytes(content)
            base_files[0].write_bytes(b"incomplete")
            self.assertFalse(runtime.models_ready)

    async def test_empty_stage_file_is_never_ready(self):
        with tempfile.TemporaryDirectory() as directory:
            ns = vdn_namespace(Path(directory))
            runtime = ns["vdn_h3_runtime"]
            for path in runtime._model_paths():
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b"x" * 1025)
            for name in ns["MODEL_FILES"]:
                path = ns["STAGE_DIR"] / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b"downloaded")
            self.assertTrue(runtime.models_ready)
            for name in ns["MODEL_FILES"]:
                with self.subTest(empty_file=name):
                    path = ns["STAGE_DIR"] / name
                    path.write_bytes(b"")
                    self.assertFalse(runtime._stage_ready())
                    self.assertFalse(runtime.models_ready)
                    path.write_bytes(b"downloaded")
                    self.assertTrue(runtime.models_ready)

    async def test_prepare_rejects_incomplete_download(self):
        with tempfile.TemporaryDirectory() as directory:
            ns = vdn_namespace(Path(directory))
            for name, revision in (("ComfyUI-ClipProj", ns["h3"].CLIPPROJ_COMMIT),
                                   ("ComfyUI-MiniMax-H3-Turbo", ns["h3"].TURBO_NODE_COMMIT),
                                   ("ComfyUI-VDN-H3", ns["NODE_COMMIT"])):
                marker = ns["ROOT"] / "custom_nodes" / name / ".neve-commit"
                marker.parent.mkdir(parents=True)
                marker.write_text(revision, encoding="utf8")
            runtime = ns["vdn_h3_runtime"]
            runtime._run_command = AsyncMock()
            with self.assertRaisesRegex(RuntimeError, "download.*nao foi concluido"):
                await runtime.prepare(AsyncMock())
            runtime._run_command.assert_awaited_once()
            self.assertFalse(runtime._stage_ready())
            self.assertFalse((ns["ROOT"] / "shared_paths.yaml").exists())

    async def test_installed_requires_original_runtime_and_current_vdn_marker(self):
        with tempfile.TemporaryDirectory() as directory:
            ns = vdn_namespace(Path(directory))
            runtime = ns["vdn_h3_runtime"]
            marker = ns["ROOT"] / "custom_nodes/ComfyUI-VDN-H3/.neve-commit"
            self.assertFalse(runtime.is_installed)
            marker.parent.mkdir(parents=True)
            marker.write_text("stale", encoding="utf8")
            self.assertFalse(runtime.is_installed)
            marker.write_text(ns["NODE_COMMIT"], encoding="utf8")
            self.assertTrue(runtime.is_installed)
            ns["h3"].minimax_h3_runtime.is_installed = False
            self.assertFalse(runtime.is_installed)

    async def test_start_server_passes_worker_hooks_to_subprocess(self):
        with tempfile.TemporaryDirectory() as directory:
            ns = vdn_namespace(Path(directory))
            runtime_class = next(n for n in ast.parse(VIDEO.read_text(encoding="utf8")).body
                                 if isinstance(n, ast.ClassDef) and n.name == "MiniMaxH3Runtime")
            start = next(n for n in runtime_class.body if getattr(n, "name", None) == "_start_server")
            launch = next(i for i, n in enumerate(start.body) if isinstance(n, ast.Assign)
                          and any(isinstance(t, ast.Attribute) and t.attr == "_process" for t in n.targets))
            # Stop before the polling/tasks: only subprocess arguments are under test.
            start.body = start.body[:launch + 1]
            spawn = AsyncMock()
            scope = dict(os=os, asyncio=SimpleNamespace(create_subprocess_exec=spawn,
                         subprocess=SimpleNamespace(PIPE=-1, STDOUT=-2)),
                         COMFYUI_DIR=Path(directory) / "ComfyUI",
                         _runtime_python=lambda: Path(directory) / "python",
                         _hidden_process_kwargs=lambda: {})
            execute([start], scope)
            for runtime in (ns["h3"].MiniMaxH3Runtime(), ns["vdn_h3_runtime"]):
                runtime.stop = AsyncMock()
                runtime._available_port = lambda: 8188
                runtime._apply_safe_power_limit = AsyncMock()
                await scope["_start_server"](runtime, AsyncMock())
                args, kwargs = spawn.await_args
                root, input_dir, output_dir, temp_dir, hf_cache = runtime._worker_paths()
                for flag, expected in (("--base-directory", root), ("--input-directory", input_dir),
                                       ("--output-directory", output_dir), ("--temp-directory", temp_dir)):
                    self.assertEqual(args[args.index(flag) + 1], str(expected))
                self.assertEqual(kwargs["env"]["HF_HOME"], str(hf_cache))
                self.assertTrue(all(p.is_dir() for p in (input_dir, output_dir, temp_dir, hf_cache)))
                extra = runtime._worker_extra_arguments()
                if extra:
                    self.assertEqual(list(args[-len(extra):]), extra)
                else:
                    self.assertNotIn("--extra-model-paths-config", args)

    async def test_inherited_cancel_interrupts_queue_and_stops_worker(self):
        ns = vdn_namespace(Path("test-cache"))
        runtime = ns["vdn_h3_runtime"]
        runtime._active_command = object()
        runtime._process = object()
        runtime._port = 8188
        runtime._prompt_id = "pending-video"
        runtime._terminate_process = AsyncMock()
        runtime.stop = AsyncMock()
        client = SimpleNamespace(post=AsyncMock())
        context = SimpleNamespace(__aenter__=AsyncMock(return_value=client), __aexit__=AsyncMock())

        class ClientContext:
            async def __aenter__(self):
                return await context.__aenter__()

            async def __aexit__(self, *args):
                return await context.__aexit__(*args)

        class HTTPError(Exception):
            pass

        globals_ = runtime.cancel.__func__.__globals__
        globals_["httpx"] = SimpleNamespace(AsyncClient=lambda **kw: ClientContext(), HTTPError=HTTPError)
        for connection_fails in (False, True):
            with self.subTest(connection_fails=connection_fails):
                runtime.stop.reset_mock()
                runtime._terminate_process.reset_mock()
                client.post.reset_mock()
                client.post.side_effect = HTTPError("offline") if connection_fails else None
                await runtime.cancel()
                self.assertTrue(runtime._cancel_requested)
                runtime._terminate_process.assert_awaited_once_with(runtime._active_command)
                self.assertEqual(client.post.await_args_list[0].args, ("http://127.0.0.1:8188/interrupt",))
                if not connection_fails:
                    self.assertEqual(client.post.await_args_list[1].args, ("http://127.0.0.1:8188/queue",))
                    self.assertEqual(client.post.await_args_list[1].kwargs, {"json": {"delete": ["pending-video"]}})
                runtime.stop.assert_awaited_once_with()

    async def test_inherited_stop_clears_process_and_restores_power(self):
        runtime = vdn_namespace(Path("test-cache"))["vdn_h3_runtime"]
        process = object()
        runtime._process = process
        runtime._port = 8188
        runtime._prompt_id = "pending-video"
        runtime._terminate_process = AsyncMock()
        runtime._restore_power_limit = AsyncMock()
        await runtime.stop()
        runtime._terminate_process.assert_awaited_once_with(process)
        runtime._restore_power_limit.assert_awaited_once_with()
        self.assertIsNone(runtime._process)
        self.assertIsNone(runtime._port)
        self.assertIsNone(runtime._prompt_id)

    async def test_prepare_reuses_original_and_only_writes_vdn_tree(self):
        with tempfile.TemporaryDirectory() as directory:
            ns = vdn_namespace(Path(directory))
            h3 = ns["h3"]
            dependencies = (("ComfyUI-ClipProj", h3.CLIPPROJ_COMMIT),
                            ("ComfyUI-MiniMax-H3-Turbo", h3.TURBO_NODE_COMMIT))
            for name, revision in dependencies:
                source = h3.COMFYUI_CUSTOM_NODES / name
                source.mkdir(parents=True)
                (source / "__init__.py").write_text("# shared node", encoding="utf8")
                (source / "grid.bin").write_bytes(b"sibling-grid")
            weight = h3.VIDEO_ROOT / "models/diffusion_models/base.safetensors"
            weight.parent.mkdir(parents=True)
            weight.write_bytes(b"original-weight")
            before = {p.relative_to(h3.VIDEO_ROOT): p.read_bytes()
                      for p in h3.VIDEO_ROOT.rglob("*") if p.is_file()}

            def install(url, target):
                self.assertIn(ns["NODE_COMMIT"], url)
                target.mkdir(parents=True)

            h3._replace_source_from_archive.side_effect = install
            runtime = ns["vdn_h3_runtime"]

            async def download(command):
                for name in ns["MODEL_FILES"]:
                    path = ns["STAGE_DIR"] / name
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(b"downloaded")

            runtime._run_command = AsyncMock(side_effect=download)
            progress = AsyncMock()
            await runtime.prepare(progress)
            h3.minimax_h3_runtime.prepare.assert_awaited_once_with(progress)
            script = ast.parse(runtime._run_command.await_args.args[0][2])
            download = script.body[1].value
            options = {kw.arg: ast.literal_eval(kw.value) for kw in download.keywords}
            self.assertEqual(options, dict(repo_id=ns["WEIGHTS_REPO"], revision=ns["WEIGHTS_REVISION"],
                                          allow_patterns=list(ns["MODEL_FILES"]), local_dir=str(ns["STAGE_DIR"])))
            self.assertEqual(len(ns["WEIGHTS_REVISION"]), 40)
            for name, revision in dependencies:
                target = ns["ROOT"] / "custom_nodes" / name
                self.assertEqual((target / "grid.bin").read_bytes(), b"sibling-grid")
                self.assertEqual((target / ".neve-commit").read_text(encoding="utf8"), revision)
            config = json.loads((ns["ROOT"] / "shared_paths.yaml").read_text(encoding="utf8"))
            self.assertEqual(config, {"neve_video_shared": {
                "base_path": str(h3.VIDEO_ROOT), "diffusion_models": "models/diffusion_models",
                "text_encoders": "models/text_encoders", "clip_projections": "models/clip_projections",
                "vae": "models/vae",
            }})
            self.assertEqual(before, {p.relative_to(h3.VIDEO_ROOT): p.read_bytes()
                                      for p in h3.VIDEO_ROOT.rglob("*") if p.is_file()})
            runtime._run_command.reset_mock()
            from unittest.mock import patch

            with patch.object(shutil, "copytree", wraps=shutil.copytree) as copy:
                await runtime.prepare(progress)
                copy.assert_not_called()
            runtime._run_command.assert_not_awaited()
            h3._replace_source_from_archive.assert_called_once()
            for name, revision in dependencies:
                with self.subTest(stale_dependency=name):
                    target = ns["ROOT"] / "custom_nodes" / name
                    (target / ".neve-commit").write_text("stale", encoding="utf8")
                    (target / "grid.bin").write_bytes(b"outdated-grid")
                    await runtime.prepare(progress)
                    self.assertEqual((target / "grid.bin").read_bytes(), b"sibling-grid")
                    self.assertEqual((target / ".neve-commit").read_text(encoding="utf8"), revision)
            runtime._run_command.assert_not_awaited()
            h3._replace_source_from_archive.assert_called_once()


class VideoVDNHandlerTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        def runtime():
            return SimpleNamespace(session_lock=asyncio.Lock(), prepare=AsyncMock(),
                                   generate=AsyncMock(return_value={"video": b"video", "filename": "test.mp4"}),
                                   stop=AsyncMock(), cancel=AsyncMock())
        self.original, self.vdn = runtime(), runtime()
        self.references = []
        self.prepared_path = SimpleNamespace(read_bytes=Mock(return_value=b"image"), unlink=Mock())
        self.events = []
        self.release = Mock()
        self.upload = Mock(return_value=SimpleNamespace(id="video-id"))

        def validate(*args, references, max_images, **kwargs):
            if len(references) > max_images:
                raise ValueError("Too many references")

        self.ns = dict(
            asyncio=asyncio, Path=Path, io=io, uuid4=uuid4,
            UploadFile=lambda **kwargs: SimpleNamespace(**kwargs),
            log=Mock(), Depends=lambda dependency: None, get_verified_user=Mock(),
            _collect_stable_diffusion_prompt=lambda *a: "Scene",
            _collect_stable_diffusion_image_references=lambda *a, **kw: self.references,
            _validate_media_attachments=validate, has_permission=lambda *a: True,
            _acquire_media_generation_slot=AsyncMock(), _release_media_generation_slot=self.release,
            video_canvas_dimensions=lambda resolution, aspect, size=None: size or (864, 480),
            model_manager=SimpleNamespace(standby=AsyncMock(return_value=None)),
            media_model_standby=media_model_standby,
            _prepare_init_image_sync=lambda *a: SimpleNamespace(width=640, height=480, path=self.prepared_path),
            minimax_h3_runtime=self.original, vdn_h3_runtime=self.vdn, upload_file_handler=self.upload,
        )
        self.handler = extracted_function(MIDDLEWARE, "chat_video_generation_handler", self.ns)
        self.request = SimpleNamespace(app=SimpleNamespace(
            state=SimpleNamespace(config=SimpleNamespace(ENABLE_VIDEO_GENERATION=True, USER_PERMISSIONS={})),
            url_path_for=lambda *a, **kw: "/video-id/content"))
        self.user = SimpleNamespace(id="test-user")

    async def invoke(self, model="vdn_h3", duration="5s"):
        self.metadata = {}
        return await self.handler(self.request, {"messages": []}, {
            "__metadata__": self.metadata, "__event_emitter__": AsyncMock(side_effect=self.events.append),
            "__features__": {"video_generation_model": model, "video_generation_duration": duration},
        }, self.user)

    async def test_model_selection_fallback_and_original_frame_counts(self):
        for model in ("vdn_h3", "minimax_h3", None, "unknown", "VDN_H3"):
            for duration, frames in (("5s", 124), ("8s", 196)):
                for count in range(3):
                    with self.subTest(model=model, duration=duration, references=count):
                        self.original.generate.reset_mock()
                        self.vdn.generate.reset_mock()
                        self.references = ["first", "last"][:count]
                        await self.invoke(model, duration)
                        chosen, other = (self.vdn, self.original) if model == "vdn_h3" else (self.original, self.vdn)
                        chosen.generate.assert_awaited_once()
                        other.generate.assert_not_awaited()
                        kwargs = chosen.generate.await_args.kwargs
                        self.assertEqual(kwargs["frames"], frames)
                        self.assertEqual(kwargs["image"] is not None, count > 0)
                        self.assertEqual(kwargs["last_image"] is not None, count == 2)
                        self.assertEqual((kwargs["width"], kwargs["height"]), (640, 480) if count else (864, 480))
                        metadata = self.upload.call_args.kwargs["metadata"]
                        self.assertEqual(metadata["video_model"], "vdn_h3" if model == "vdn_h3" else "minimax_h3")
                        if model in ("vdn_h3", "minimax_h3"):
                            self.assertEqual(metadata["video_model"], model)
                        self.assertEqual(metadata["source"], "minimax-h3-vdn-int8" if model == "vdn_h3" else "minimax-h3-fl2va-w4a8")
                        # Generated-video library queries accept this source family.
                        self.assertTrue(metadata["source"].startswith("minimax-h3-"))
                        self.assertTrue(self.metadata["skip_llm"])
                        self.release.assert_called_with(True)

    async def test_cancellation_during_prepare_and_generation_cleans_selected_worker(self):
        for model in ("vdn_h3", "minimax_h3"):
            for phase in ("prepare", "generate"):
                with self.subTest(model=model, phase=phase):
                    self.setUp()
                    chosen, other = (self.vdn, self.original) if model == "vdn_h3" else (self.original, self.vdn)
                    self.references = ["first", "last"]
                    getattr(chosen, phase).side_effect = asyncio.CancelledError()
                    with self.assertRaises(asyncio.CancelledError):
                        await self.invoke(model)
                    self.assertGreaterEqual(chosen.stop.await_count, 1)
                    other.stop.assert_not_awaited()
                    self.assertFalse(chosen.session_lock.locked())
                    self.release.assert_called_once_with(True)
                    self.upload.assert_not_called()
                    self.assertTrue(self.metadata["skip_llm"])
                    if phase == "generate":
                        self.assertEqual(self.prepared_path.unlink.call_count, 2)

    async def test_extra_reference_rejected_before_acquiring_slot(self):
        self.references = ["first", "last", "third"]
        await self.invoke()
        self.vdn.prepare.assert_not_awaited()
        self.original.prepare.assert_not_awaited()
        self.ns["_acquire_media_generation_slot"].assert_not_awaited()
        self.release.assert_called_once_with(False)
        self.upload.assert_not_called()
        self.assertTrue(any(e["type"] == "status" and e["data"].get("error") for e in self.events))

    async def test_cancel_endpoint_cancels_both_workers(self):
        cancel = extracted_function(VIDEO, "cancel_video_generation", self.ns)
        self.assertEqual(await cancel(self.request, self.user), {"success": True})
        self.original.cancel.assert_awaited_once_with()
        self.vdn.cancel.assert_awaited_once_with()

    async def test_status_running_and_readiness_are_scoped_to_each_model(self):
        status = extracted_function(VIDEO, "get_video_generation_status", self.ns)
        for mask in range(16):
            original_running, vdn_running, original_ready, vdn_ready = (
                bool(mask & (1 << bit)) for bit in range(4)
            )
            with self.subTest(mask=mask):
                self.original.is_installed = True
                self.original.is_running = original_running
                self.vdn.is_running = vdn_running
                self.original.models_ready = original_ready
                self.vdn.models_ready = vdn_ready
                result = await status(self.request, self.user)
                self.assertEqual(result["running"], original_running or vdn_running)
                self.assertEqual(result["models_ready"], original_ready)
                self.assertEqual(result["models"]["minimax_h3"]["ready"], original_ready)
                self.assertEqual(result["models"]["vdn_h3"]["ready"], vdn_ready)


class VideoSubmittedFeaturesTests(unittest.TestCase):
    def test_submitted_video_choice_survives_rebuilt_payload(self):
        tree = ast.parse(MIDDLEWARE.read_text(encoding="utf8"))
        owner = next(n for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef)
                     and any(isinstance(s, ast.Assign) and any(isinstance(t, ast.Name)
                             and t.id == "submitted_features" for t in s.targets) for s in n.body))
        start = next(i for i, n in enumerate(owner.body) if isinstance(n, ast.Assign)
                     and any(isinstance(t, ast.Name) and t.id == "features" for t in n.targets))
        end = next(i for i in range(start, len(owner.body)) if isinstance(owner.body[i], ast.Assign)
                   and any(isinstance(t, ast.Subscript) and isinstance(t.value, ast.Name)
                           and t.value.id == "extra_params" for t in owner.body[i].targets))
        for model in ("vdn_h3", "minimax_h3", "unknown", None):
            with self.subTest(model=model):
                submitted = dict(video_generation=True, video_generation_model=model,
                                 video_generation_resolution="672p", video_generation_duration="8s",
                                 video_generation_aspect_ratio="9:16")
                conflicts = ("web_search", "deep_search", "code_execution", "file_generation",
                             "stable_diffusion", "music_generation")
                scope = dict(form_data={"features": {**dict.fromkeys(conflicts, True), "video_generation_model": "overwritten"}},
                             metadata={"features": submitted.copy()}, extra_params={})
                execute(owner.body[start:end + 1], scope)
                restored = scope["extra_params"]["__features__"]
                self.assertTrue(restored["video_generation"])
                self.assertEqual(restored["video_generation_model"], "vdn_h3" if model == "vdn_h3" else "minimax_h3")
                for key in ("video_generation_resolution", "video_generation_duration", "video_generation_aspect_ratio"):
                    self.assertEqual(restored[key], submitted[key])
                self.assertTrue(all(restored[k] is False for k in conflicts))
                self.assertEqual(scope["metadata"]["features"], submitted)


if __name__ == "__main__":
    unittest.main()
