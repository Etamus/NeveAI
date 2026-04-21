"""
SDXL Lightning Local — GPU-based image generation using SDXL Lightning 4-step.

Uses ByteDance/SDXL-Lightning UNet checkpoint over the SDXL base 1.0 pipeline.
Manages loading/unloading the diffusion pipeline and coordinates VRAM with
the llama-server (LLM) via the LocalModelManager standby/resume mechanism.
"""

import asyncio
import base64
import io
import logging
import time
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from neveai.constants import ERROR_MESSAGES
from neveai.utils.auth import get_admin_user, get_verified_user
from neveai.utils.access_control import has_permission
from neveai.config import CACHE_DIR

log = logging.getLogger(__name__)

router = APIRouter()

# ---------------------------------------------------------------------------
# Pipeline Manager
# ---------------------------------------------------------------------------

SD_CACHE_DIR = CACHE_DIR / "stable_diffusion"
SD_CACHE_DIR.mkdir(parents=True, exist_ok=True)

IMAGE_OUTPUT_DIR = CACHE_DIR / "image" / "generations"
IMAGE_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


class _SDPipeline:
    """Manages the SDXL Lightning 4-step diffusion pipeline lifecycle."""

    def __init__(self):
        self._pipe = None
        self._model_id: Optional[str] = None
        self._lock = asyncio.Lock()
        self._loaded = False

    @property
    def is_loaded(self) -> bool:
        return self._loaded and self._pipe is not None

    async def load(self, model_id: str, device: str = "cuda"):
        """Load the diffusion pipeline onto GPU.

        from_pretrained e .to(device) são síncronos/bloqueantes.
        Rodam em thread pool para nunca bloquear o event loop do FastAPI
        (evita travamento do console e do servidor durante download/load).
        """
        async with self._lock:
            if self._loaded and self._model_id == model_id:
                return  # Already loaded

            await self._unload_internal()

            log.info(f"Loading Stable Diffusion pipeline: {model_id}")

            loop = asyncio.get_event_loop()

            def _load_sync():
                import torch
                from diffusers import (
                    StableDiffusionXLPipeline,
                    UNet2DConditionModel,
                    EulerDiscreteScheduler,
                )
                from huggingface_hub import hf_hub_download
                from safetensors.torch import load_file

                _base = "stabilityai/stable-diffusion-xl-base-1.0"
                _lightning_repo = "ByteDance/SDXL-Lightning"
                _lightning_ckpt = "sdxl_lightning_4step_unet.safetensors"

                # Load Lightning UNet weights onto GPU
                unet = UNet2DConditionModel.from_config(
                    _base, subfolder="unet"
                ).to(device, torch.float16)
                unet.load_state_dict(
                    load_file(
                        hf_hub_download(
                            _lightning_repo,
                            _lightning_ckpt,
                            cache_dir=str(SD_CACHE_DIR),
                        ),
                        device=device,
                    )
                )

                # Build pipeline from SDXL base, substituting the Lightning UNet
                pipe = StableDiffusionXLPipeline.from_pretrained(
                    _base,
                    unet=unet,
                    torch_dtype=torch.float16,
                    variant="fp16",
                    cache_dir=str(SD_CACHE_DIR),
                ).to(device)

                # Lightning requires EulerDiscrete with trailing timesteps
                pipe.scheduler = EulerDiscreteScheduler.from_config(
                    pipe.scheduler.config,
                    timestep_spacing="trailing",
                    prediction_type="epsilon",
                )

                return pipe

            self._pipe = await loop.run_in_executor(None, _load_sync)
            self._model_id = model_id
            self._loaded = True
            log.info(f"Stable Diffusion pipeline loaded: {model_id}")

    async def unload(self):
        """Unload pipeline and free VRAM."""
        async with self._lock:
            await self._unload_internal()

    async def _unload_internal(self):
        if self._pipe is not None:
            log.info(f"Unloading Stable Diffusion pipeline: {self._model_id}")
            del self._pipe
            self._pipe = None
            self._loaded = False
            self._model_id = None
            # Force CUDA memory release
            try:
                import torch
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
        steps: int = 4,
        guidance_scale: float = 0.0,
    ) -> str:
        """Generate an image and return base64-encoded PNG data URI."""
        if not self.is_loaded:
            raise RuntimeError("Stable Diffusion pipeline not loaded")

        import torch

        loop = asyncio.get_event_loop()

        def _run():
            with torch.no_grad():
                result = self._pipe(
                    prompt=prompt,
                    width=width,
                    height=height,
                    num_inference_steps=4,   # Fixed: SDXL Lightning 4-step
                    guidance_scale=0.0,      # Fixed: CFG-free for Lightning
                )
            return result.images[0]

        image = await loop.run_in_executor(None, _run)

        # Save to file and return as data URI
        buf = io.BytesIO()
        image.save(buf, format="PNG")
        buf.seek(0)

        b64 = base64.b64encode(buf.getvalue()).decode("utf-8")

        # Also save to cache
        filename = f"sd_{int(time.time())}.png"
        filepath = IMAGE_OUTPUT_DIR / filename
        with open(filepath, "wb") as f:
            f.write(buf.getvalue())

        return f"data:image/png;base64,{b64}"


# Singleton pipeline manager
_sd_pipeline = _SDPipeline()


# ---------------------------------------------------------------------------
# API Models
# ---------------------------------------------------------------------------

class GenerateForm(BaseModel):
    prompt: str
    width: Optional[int] = None
    height: Optional[int] = None
    steps: Optional[int] = None
    guidance_scale: Optional[float] = None


class ConfigForm(BaseModel):
    ENABLE_STABLE_DIFFUSION: Optional[bool] = None
    STABLE_DIFFUSION_MODEL: Optional[str] = None
    STABLE_DIFFUSION_WIDTH: Optional[int] = None
    STABLE_DIFFUSION_HEIGHT: Optional[int] = None
    STABLE_DIFFUSION_STEPS: Optional[int] = None
    STABLE_DIFFUSION_GUIDANCE_SCALE: Optional[float] = None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/config")
async def get_sd_config(request: Request, user=Depends(get_admin_user)):
    return {
        "ENABLE_STABLE_DIFFUSION": request.app.state.config.ENABLE_STABLE_DIFFUSION,
        "STABLE_DIFFUSION_MODEL": request.app.state.config.STABLE_DIFFUSION_MODEL,
        "STABLE_DIFFUSION_WIDTH": request.app.state.config.STABLE_DIFFUSION_WIDTH,
        "STABLE_DIFFUSION_HEIGHT": request.app.state.config.STABLE_DIFFUSION_HEIGHT,
        "STABLE_DIFFUSION_STEPS": request.app.state.config.STABLE_DIFFUSION_STEPS,
        "STABLE_DIFFUSION_GUIDANCE_SCALE": request.app.state.config.STABLE_DIFFUSION_GUIDANCE_SCALE,
        "is_loaded": _sd_pipeline.is_loaded,
    }


@router.post("/config/update")
async def update_sd_config(
    request: Request,
    form_data: ConfigForm,
    user=Depends(get_admin_user),
):
    if form_data.ENABLE_STABLE_DIFFUSION is not None:
        request.app.state.config.ENABLE_STABLE_DIFFUSION = form_data.ENABLE_STABLE_DIFFUSION
    if form_data.STABLE_DIFFUSION_MODEL is not None:
        request.app.state.config.STABLE_DIFFUSION_MODEL = form_data.STABLE_DIFFUSION_MODEL
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
async def generate_image(
    request: Request,
    form_data: GenerateForm,
    user=Depends(get_verified_user),
):
    if not request.app.state.config.ENABLE_STABLE_DIFFUSION:
        raise HTTPException(status_code=403, detail="Stable Diffusion is disabled")

    if not has_permission(
        user.id, "features.stable_diffusion", request.app.state.config.USER_PERMISSIONS
    ):
        raise HTTPException(status_code=403, detail=ERROR_MESSAGES.ACCESS_PROHIBITED)

    # Get config values
    model_id = request.app.state.config.STABLE_DIFFUSION_MODEL
    width = form_data.width or request.app.state.config.STABLE_DIFFUSION_WIDTH
    height = form_data.height or request.app.state.config.STABLE_DIFFUSION_HEIGHT
    steps = form_data.steps or request.app.state.config.STABLE_DIFFUSION_STEPS
    guidance_scale = form_data.guidance_scale if form_data.guidance_scale is not None else request.app.state.config.STABLE_DIFFUSION_GUIDANCE_SCALE

    # --- VRAM Management: Put LLM in standby ---
    from neveai.routers.llamacpp import model_manager
    llm_was_loaded = False
    llm_standby_info = None

    try:
        llm_standby_info = await model_manager.standby()
        llm_was_loaded = llm_standby_info is not None
    except Exception as e:
        log.warning(f"Failed to put LLM in standby: {e}")

    try:
        # Load SD pipeline
        await _sd_pipeline.load(model_id)

        # Generate image
        data_uri = await _sd_pipeline.generate(
            prompt=form_data.prompt,
            width=width,
            height=height,
            steps=steps,
            guidance_scale=guidance_scale,
        )

        return {"url": data_uri}

    finally:
        # --- VRAM Management: Unload SD and resume LLM ---
        try:
            await _sd_pipeline.unload()
        except Exception as e:
            log.warning(f"Failed to unload SD pipeline: {e}")

        if llm_was_loaded and llm_standby_info:
            try:
                await model_manager.resume(llm_standby_info)
            except Exception as e:
                log.warning(f"Failed to resume LLM from standby: {e}")


@router.post("/load")
async def load_sd_pipeline(request: Request, user=Depends(get_admin_user)):
    """Manually load the SD pipeline (admin only)."""
    if not request.app.state.config.ENABLE_STABLE_DIFFUSION:
        raise HTTPException(status_code=403, detail="Stable Diffusion is disabled")

    model_id = request.app.state.config.STABLE_DIFFUSION_MODEL
    await _sd_pipeline.load(model_id)
    return {"status": "loaded", "model": model_id}


@router.post("/unload")
async def unload_sd_pipeline(request: Request, user=Depends(get_admin_user)):
    """Manually unload the SD pipeline (admin only)."""
    await _sd_pipeline.unload()
    return {"status": "unloaded"}
