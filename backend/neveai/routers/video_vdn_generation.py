"""VDN-H3 adapters in a separate ComfyUI worker; the original H3 stays unchanged."""
from __future__ import annotations

import asyncio
import json
import shutil
from pathlib import Path

from neveai.config import CACHE_DIR
from neveai.routers import video_generation as h3

ROOT = CACHE_DIR / "video_vdn_generation"
NODE_COMMIT = "3eb63496c24ca70faaf8a14b6c75fcb480e34bf1"
STAGE = "stage-dmd-step-250-int8_convrot_comfyui"
STAGE_DIR = ROOT / "models" / "vdn" / STAGE
WEIGHTS_REPO = "drbaph/vdn-minimax-h3-int8-convrot-comfyui"
WEIGHTS_REVISION = "3dc26acabfa4cfc808faf6be0bf20b5e070897a4"
MODEL_FILES = (
    "model_spec.json", "linear_branch/config.json",
    "linear_branch/model_int8_convrot_comfyui.safetensors",
    "adapters/default/adapter_config.json", "adapters/default/adapter_model.safetensors",
    "adapters/turbo/adapter_config.json", "adapters/turbo/adapter_model.safetensors",
)


class VDNH3Runtime(h3.MiniMaxH3Runtime):
    @property
    def is_installed(self) -> bool:
        marker = ROOT / "custom_nodes" / "ComfyUI-VDN-H3" / ".neve-commit"
        try:
            return (h3.minimax_h3_runtime.is_installed
                    and marker.read_text(encoding="utf-8").strip() == NODE_COMMIT)
        except OSError:
            return False

    @property
    def models_ready(self) -> bool:
        return super().models_ready and self._stage_ready()

    @staticmethod
    def _stage_ready() -> bool:
        return all((STAGE_DIR / name).is_file() and (STAGE_DIR / name).stat().st_size > 0
                   for name in MODEL_FILES)

    async def prepare(self, progress):
        await h3.minimax_h3_runtime.prepare(progress)
        async with self._runtime_lock:
            # VDN's pruned-base adapter reads the Turbo grid by sibling path.
            for name, revision in (("ComfyUI-ClipProj", h3.CLIPPROJ_COMMIT),
                                   ("ComfyUI-MiniMax-H3-Turbo", h3.TURBO_NODE_COMMIT)):
                target = ROOT / "custom_nodes" / name
                dependency_marker = target / ".neve-commit"
                if not dependency_marker.is_file() or dependency_marker.read_text().strip() != revision:
                    await asyncio.to_thread(shutil.copytree, h3.COMFYUI_CUSTOM_NODES / name, target,
                                            dirs_exist_ok=True)
                    dependency_marker.write_text(revision, encoding="utf-8")
            node_dir = ROOT / "custom_nodes" / "ComfyUI-VDN-H3"
            marker = node_dir / ".neve-commit"
            if not marker.is_file() or marker.read_text().strip() != NODE_COMMIT:
                await progress("Preparando o Neve Video 1.5...")
                await asyncio.to_thread(h3._replace_source_from_archive,
                    f"https://github.com/Saganaki22/ComfyUI-VDN-H3/archive/{NODE_COMMIT}.zip", node_dir)
                marker.write_text(NODE_COMMIT, encoding="utf-8")
            if not self._stage_ready():
                await progress("Baixando os modelos do Neve Video 1.5...")
                script = (
                    "from huggingface_hub import snapshot_download; "
                    f"snapshot_download(repo_id={WEIGHTS_REPO!r}, revision={WEIGHTS_REVISION!r}, "
                    f"allow_patterns={list(MODEL_FILES)!r}, local_dir={str(STAGE_DIR)!r})"
                )
                await self._run_command([str(h3._runtime_python()), "-c", script])
                if not self._stage_ready():
                    raise RuntimeError("O download dos modelos do Neve Video 1.5 nao foi concluido.")
            # JSON is a YAML subset accepted by ComfyUI; shared weights are read-only.
            paths = {"neve_video_shared": {"base_path": str(h3.VIDEO_ROOT),
                "diffusion_models": "models/diffusion_models", "text_encoders": "models/text_encoders",
                "clip_projections": "models/clip_projections", "vae": "models/vae"}}
            (ROOT / "shared_paths.yaml").write_text(json.dumps(paths), encoding="utf-8")

    def _worker_paths(self):
        return ROOT, ROOT / "input", ROOT / "output", ROOT / "temp", ROOT / "huggingface"

    def _worker_extra_arguments(self):
        return ["--extra-model-paths-config", str(ROOT / "shared_paths.yaml"), "--disable-comfy-compiler"]

    @staticmethod
    def _build_workflow(prompt, seed, input_image, last_image=None, width=h3.DEFAULT_WIDTH,
                        height=h3.DEFAULT_HEIGHT, frames=h3.DEFAULT_FRAMES, low_vram_lora=True):
        workflow = h3.MiniMaxH3Runtime._build_workflow(
            prompt, seed, input_image, last_image, width, height, frames, low_vram_lora)
        workflow["7"] = {"class_type": "ApplyVDNH3", "inputs": {
            "model": ["6", 0], "vdn_checkpoint": STAGE, "apply_turbo_adapter": True,
            "strength": 1.0, "lora_mode": "merge", "branch_weights": "stream",
            "retain_buffers": "off", "attention_backend": "grouped", "verbose": False,
        }}
        workflow["9"]["inputs"]["scheduler"] = "beta"
        workflow["11"] = {"class_type": "KSamplerSelect", "inputs": {"sampler_name": "er_sde"}}
        return workflow


vdn_h3_runtime = VDNH3Runtime()
