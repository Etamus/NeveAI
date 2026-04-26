"""
Z-Image-Turbo Local -- Geracao de imagem com transformer GGUF pre-quantizado.

Fluxo de carga:
    1. Baixa/carrega z-image-turbo-Q4_K_M.gguf ja quantizado
    2. Injeta o transformer GGUF no ZImagePipeline diffusers
    3. Move pipeline para CUDA

Sem quantizacao em runtime, sem torch.compile e sem JIT durante o request.
Qualidade: Q4_K_M GGUF Unsloth, melhor equilibrio entre rapidez, VRAM e qualidade.
Resolucao: 768 x 768
Steps    : 6  (guidance_scale=0.0 -- modelo turbo nao usa CFG)
Modo     : somente txt2img
"""

import asyncio
import base64
import io
import logging
import time
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from neveai.constants import ERROR_MESSAGES
from neveai.utils.auth import get_admin_user, get_verified_user
from neveai.utils.access_control import has_permission
from neveai.config import CACHE_DIR, STABLE_DIFFUSION_HF_TOKEN

log = logging.getLogger(__name__)
router = APIRouter()

IMAGE_OUTPUT_DIR = CACHE_DIR / "image" / "generations"
IMAGE_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

SD_CACHE_DIR = CACHE_DIR / "stable_diffusion"
GGUF_CACHE_DIR = SD_CACHE_DIR / "gguf"
PIPELINE_CACHE_DIR = SD_CACHE_DIR / "pipeline"
GGUF_CACHE_DIR.mkdir(parents=True, exist_ok=True)
PIPELINE_CACHE_DIR.mkdir(parents=True, exist_ok=True)

ZIMAGE_BASE_REPO = "Tongyi-MAI/Z-Image-Turbo"
ZIMAGE_GGUF_REPO = "unsloth/Z-Image-Turbo-GGUF"
ZIMAGE_GGUF_FILE = "z-image-turbo-Q4_K_M.gguf"


class _ZImagePipeline:
    """Gerencia o pipeline Z-Image-Turbo."""

    def __init__(self):
        self._pipe = None
        self._model_id: Optional[str] = None
        self._lock = asyncio.Lock()
        self._loaded = False

    @property
    def is_loaded(self) -> bool:
        return self._loaded and self._pipe is not None

    async def load(self, model_id: str, device: str = "cuda", hf_token: Optional[str] = None):
        async with self._lock:
            if self._loaded and self._model_id == model_id:
                return
            await self._unload_internal()
            log.info(f"Carregando Z-Image-Turbo GGUF: {ZIMAGE_GGUF_REPO}/{ZIMAGE_GGUF_FILE}")
            loop = asyncio.get_event_loop()

            def _load_sync():
                import gc
                import torch
                from diffusers import (
                    GGUFQuantizationConfig,
                    ZImagePipeline,
                    ZImageTransformer2DModel,
                )
                from huggingface_hub import hf_hub_download

                torch.backends.cuda.matmul.allow_tf32 = True
                torch.backends.cudnn.allow_tf32 = True

                log.info("Baixando/carregando transformer GGUF pre-quantizado...")
                gguf_path = hf_hub_download(
                    repo_id=ZIMAGE_GGUF_REPO,
                    filename=ZIMAGE_GGUF_FILE,
                    cache_dir=str(GGUF_CACHE_DIR),
                    token=hf_token or None,
                )

                transformer = ZImageTransformer2DModel.from_single_file(
                    gguf_path,
                    quantization_config=GGUFQuantizationConfig(compute_dtype=torch.bfloat16),
                    dtype=torch.bfloat16,
                )

                log.info("Carregando VAE/text encoder/tokenizer do Z-Image-Turbo base...")
                pipe = ZImagePipeline.from_pretrained(
                    ZIMAGE_BASE_REPO,
                    transformer=transformer,
                    dtype=torch.bfloat16,
                    low_cpu_mem_usage=True,
                    cache_dir=str(PIPELINE_CACHE_DIR),
                    token=hf_token or None,
                )

                pipe.to(device)

                gc.collect()
                torch.cuda.empty_cache()

                log.info(
                    "Z-Image-Turbo GGUF pronto. VRAM: %.1f GB",
                    torch.cuda.memory_allocated() / 1e9,
                )
                return pipe

            self._pipe = await loop.run_in_executor(None, _load_sync)
            self._model_id = model_id
            self._loaded = True

    async def unload(self):
        async with self._lock:
            await self._unload_internal()

    async def _unload_internal(self):
        if self._pipe is not None:
            del self._pipe
            self._pipe = None
            self._loaded = False
            self._model_id = None
            try:
                import gc, torch
                gc.collect()
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
                    torch.cuda.synchronize()
            except Exception:
                pass

    async def generate(
        self,
        prompt: str,
        width: int = 768,
        height: int = 768,
        steps: int = 6,
        guidance_scale: float = 0.0,
    ) -> str:
        if not self.is_loaded:
            raise RuntimeError("Z-Image pipeline nao carregado")

        import torch
        loop = asyncio.get_event_loop()

        def _run():
            with torch.no_grad():
                result = self._pipe(
                    prompt=prompt,
                    height=height,
                    width=width,
                    num_inference_steps=steps,
                    guidance_scale=guidance_scale,
                )
            return result.images[0]

        image = await loop.run_in_executor(None, _run)
        buf = io.BytesIO()
        image.save(buf, format="PNG")
        buf.seek(0)
        raw = buf.getvalue()
        b64 = base64.b64encode(raw).decode("utf-8")
        filename = f"sd_{int(time.time())}.png"
        with open(IMAGE_OUTPUT_DIR / filename, "wb") as f:
            f.write(raw)
        return f"data:image/png;base64,{b64}"


_sd_pipeline = _ZImagePipeline()  # singleton de modulo


class GenerateForm(BaseModel):
    prompt: str
    width: Optional[int] = None
    height: Optional[int] = None
    steps: Optional[int] = None
    guidance_scale: Optional[float] = None


class ConfigForm(BaseModel):
    ENABLE_STABLE_DIFFUSION:         Optional[bool]  = None
    STABLE_DIFFUSION_MODEL:          Optional[str]   = None
    STABLE_DIFFUSION_HF_TOKEN:       Optional[str]   = None
    STABLE_DIFFUSION_WIDTH:          Optional[int]   = None
    STABLE_DIFFUSION_HEIGHT:         Optional[int]   = None
    STABLE_DIFFUSION_STEPS:          Optional[int]   = None
    STABLE_DIFFUSION_GUIDANCE_SCALE: Optional[float] = None


@router.get("/config")
async def get_sd_config(request: Request, user=Depends(get_admin_user)):
    return {
        "ENABLE_STABLE_DIFFUSION":         request.app.state.config.ENABLE_STABLE_DIFFUSION,
        "STABLE_DIFFUSION_MODEL":          request.app.state.config.STABLE_DIFFUSION_MODEL,
        "STABLE_DIFFUSION_HF_TOKEN":       request.app.state.config.STABLE_DIFFUSION_HF_TOKEN,
        "STABLE_DIFFUSION_WIDTH":          request.app.state.config.STABLE_DIFFUSION_WIDTH,
        "STABLE_DIFFUSION_HEIGHT":         request.app.state.config.STABLE_DIFFUSION_HEIGHT,
        "STABLE_DIFFUSION_STEPS":          request.app.state.config.STABLE_DIFFUSION_STEPS,
        "STABLE_DIFFUSION_GUIDANCE_SCALE": request.app.state.config.STABLE_DIFFUSION_GUIDANCE_SCALE,
        "is_loaded": _sd_pipeline.is_loaded,
    }


@router.post("/config/update")
async def update_sd_config(request: Request, form_data: ConfigForm, user=Depends(get_admin_user)):
    if form_data.ENABLE_STABLE_DIFFUSION is not None:
        request.app.state.config.ENABLE_STABLE_DIFFUSION = form_data.ENABLE_STABLE_DIFFUSION
    if form_data.STABLE_DIFFUSION_MODEL is not None:
        request.app.state.config.STABLE_DIFFUSION_MODEL = form_data.STABLE_DIFFUSION_MODEL
    if form_data.STABLE_DIFFUSION_HF_TOKEN is not None:
        request.app.state.config.STABLE_DIFFUSION_HF_TOKEN = form_data.STABLE_DIFFUSION_HF_TOKEN
    if form_data.STABLE_DIFFUSION_WIDTH is not None:
        request.app.state.config.STABLE_DIFFUSION_WIDTH = form_data.STABLE_DIFFUSION_WIDTH
    if form_data.STABLE_DIFFUSION_HEIGHT is not None:
        request.app.state.config.STABLE_DIFFUSION_HEIGHT = form_data.STABLE_DIFFUSION_HEIGHT
    if form_data.STABLE_DIFFUSION_STEPS is not None:
        request.app.state.config.STABLE_DIFFUSION_STEPS = form_data.STABLE_DIFFUSION_STEPS
    if form_data.STABLE_DIFFUSION_GUIDANCE_SCALE is not None:
        request.app.state.config.STABLE_DIFFUSION_GUIDANCE_SCALE = form_data.STABLE_DIFFUSION_GUIDANCE_SCALE
    return await get_sd_config(request, user)


@router.get("/status")
async def get_sd_status(request: Request, user=Depends(get_verified_user)):
    return {
        "is_loaded": _sd_pipeline.is_loaded,
        "enabled": request.app.state.config.ENABLE_STABLE_DIFFUSION,
    }


@router.post("/generate")
async def generate_image(request: Request, form_data: GenerateForm, user=Depends(get_verified_user)):
    if not request.app.state.config.ENABLE_STABLE_DIFFUSION:
        raise HTTPException(status_code=403, detail="Stable Diffusion is disabled")
    if not has_permission(user.id, "features.stable_diffusion", request.app.state.config.USER_PERMISSIONS):
        raise HTTPException(status_code=403, detail=ERROR_MESSAGES.ACCESS_PROHIBITED)

    model_id       = request.app.state.config.STABLE_DIFFUSION_MODEL
    width          = form_data.width  or request.app.state.config.STABLE_DIFFUSION_WIDTH
    height         = form_data.height or request.app.state.config.STABLE_DIFFUSION_HEIGHT
    steps          = form_data.steps  or request.app.state.config.STABLE_DIFFUSION_STEPS
    guidance_scale = (
        form_data.guidance_scale
        if form_data.guidance_scale is not None
        else request.app.state.config.STABLE_DIFFUSION_GUIDANCE_SCALE
    )

    from neveai.routers.llamacpp import model_manager
    llm_standby_info = None
    try:
        llm_standby_info = await model_manager.standby()
    except Exception as e:
        log.warning(f"Failed to put LLM in standby: {e}")

    try:
        hf_token = str(request.app.state.config.STABLE_DIFFUSION_HF_TOKEN) or None
        await _sd_pipeline.load(model_id, hf_token=hf_token)
        data_uri = await _sd_pipeline.generate(
            prompt=form_data.prompt,
            width=width,
            height=height,
            steps=steps,
            guidance_scale=guidance_scale,
        )
        return {"url": data_uri}
    finally:
        if llm_standby_info is not None:
            try:
                from neveai.routers.llamacpp import model_manager as mm
                await mm.restore(llm_standby_info)
            except Exception as e:
                log.warning(f"Failed to restore LLM from standby: {e}")