"""Neve Video 1.5: W6A8 diffusion with the original projected 4B encoder.

The public id remains vdn_h3 for saved chats and settings compatibility.
Prompts, sampling, audio and cancellation use the shared H3 pipeline.
"""
from __future__ import annotations

import asyncio

from neveai.routers import video_generation as h3

DIFFUSION_MODEL = "minimax_h3_fl2va_pruned_w6a8.safetensors"
MODEL_REPO = "Comfy-Org/MiniMax-H3"
MODEL_REVISION = "912b6e38b2092ec4d2e86d24183e0d59ea059d48"
MODEL_SIZE = 15983746636
MODEL_PATH = h3.COMFYUI_MODELS / "diffusion_models" / DIFFUSION_MODEL


class NeveVideo15Runtime(h3.MiniMaxH3Runtime):
    @staticmethod
    def _model_paths():
        return (*h3.MiniMaxH3Runtime._model_paths(), MODEL_PATH)

    @staticmethod
    def _quality_model_ready():
        return MODEL_PATH.is_file() and MODEL_PATH.stat().st_size == MODEL_SIZE

    @property
    def models_ready(self):
        return super().models_ready and self._quality_model_ready()

    async def prepare(self, progress):
        await h3.minimax_h3_runtime.prepare(progress)
        async with self._runtime_lock:
            if self._quality_model_ready():
                return
            await progress("Baixando o modelo do Neve Video 1.5...")
            script = (
                "import os; os.environ['HF_HUB_DISABLE_XET']='1'; "
                "from huggingface_hub import hf_hub_download; "
                f"hf_hub_download(repo_id={MODEL_REPO!r}, revision={MODEL_REVISION!r}, "
                f"filename={'diffusion_models/' + DIFFUSION_MODEL!r}, "
                f"local_dir={str(h3.COMFYUI_MODELS)!r}, force_download={MODEL_PATH.exists()!r})"
            )
            task = asyncio.create_task(self._run_command([str(h3._runtime_python()), "-c", script]))
            try:
                while not task.done():
                    await asyncio.sleep(2)
                    await progress("Baixando o modelo do Neve Video 1.5...")
                await task
            finally:
                if not task.done():
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass
            if not self._quality_model_ready():
                raise RuntimeError("O download do modelo do Neve Video 1.5 nao foi concluido.")

    @staticmethod
    def _build_workflow(prompt, seed, input_image, last_image=None, width=h3.DEFAULT_WIDTH,
                        height=h3.DEFAULT_HEIGHT, frames=h3.DEFAULT_FRAMES, low_vram_lora=True):
        graph = h3.MiniMaxH3Runtime._build_workflow(
            prompt, seed, input_image, last_image, width, height, frames, low_vram_lora)
        graph["6"]["inputs"]["unet_name"] = DIFFUSION_MODEL
        return graph


video15_runtime = NeveVideo15Runtime()
