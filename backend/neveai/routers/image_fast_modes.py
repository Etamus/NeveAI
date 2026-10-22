"""Opt-in editing modes for Neve Image 2 Turbo; never used by other image models."""

import asyncio
import base64
import io
import math
from pathlib import Path
from typing import Literal, Optional
from uuid import uuid4

from PIL import Image, ImageChops, ImageFilter, ImageOps
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from neveai.routers import image_fast_generation as fast

_MODE_LOCK = asyncio.Lock()
_VERIFIED_MODE_ASSETS = {}


class ImageModeOptions(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    mode: Literal["normal", "auto", "consistent", "outfit", "outpaint", "inpaint", "head", "body", "restore"] = "normal"
    strength: float = Field(default=1.0, ge=0, le=1.5)
    auto_prompt: bool = False
    mask: Optional[str] = Field(default=None, max_length=12_000_000)
    grow: int = Field(default=8, ge=0, le=64)
    feather: int = Field(default=8, ge=0, le=64)
    rotation: float = Field(default=0, ge=-45, le=45)
    pad_left: int = Field(default=0, ge=0, le=100)
    pad_right: int = Field(default=25, ge=0, le=100)
    pad_top: int = Field(default=0, ge=0, le=100)
    pad_bottom: int = Field(default=0, ge=0, le=100)
    crop: Optional[tuple[float, float, float, float]] = None
    target: str = Field(default="the person", max_length=300)
    reference_labels: list[str] = Field(default_factory=list, max_length=9)
    reference_crops: list[Optional[tuple[float, float, float, float]]] = Field(default_factory=list, max_length=9)
    source_id: Optional[str] = Field(default=None, max_length=500)
    upscale: Literal[1, 2] = 1

    @field_validator("reference_labels")
    @classmethod
    def bound_labels(cls, labels):
        if any(len(label) > 160 for label in labels):
            raise ValueError("Descricao de referencia excede 160 caracteres.")
        return labels

    @field_validator("crop", "reference_crops")
    @classmethod
    def valid_crops(cls, value, info):
        for rect in (value if info.field_name == "reference_crops" else [value]):
            if rect is None:
                continue
            x, y, w, h = rect
            if not all(math.isfinite(n) for n in rect) or not (0 <= x < 1 and 0 <= y < 1 and 0 < w <= 1 - x + 1e-9 and 0 < h <= 1 - y + 1e-9):
                raise ValueError("Recorte invalido.")
        return value

    @model_validator(mode="after")
    def mask_uses_whole_source(self):
        if self.mode == "inpaint" and self.crop is not None:
            raise ValueError("A mascara deve usar a imagem principal inteira.")
        return self


# Revisions and digests are pinned; no arbitrary URL or local path is accepted.
ASSETS = {
    "consistent": ("ausboss/Qwen-Image-2.1-Consistency-LoRA", "1b58c4406925d6ec5fa9abd2d080531030f7cc0d", "qwen-image-2.1-consistency.safetensors", 159436496, "4f44ada1be2189cc23b3d010f9603543403f48454e2f76842a3d30109b20bd63"),
    "outfit": ("ausboss/Qwen-Image-2.1-Outfit-Swap-Consistency-LoRA", "3ae2a126eff7c3eb4e3721d89a6f9f06a1f61704", "qwen-image-2.1-outfit-swap.safetensors", 159436488, "4ddfeac5695adaed1f0f78b23fda40919fd2ed6a4af790ced6c1e043dc4ae1f0"),
    "outpaint": ("ausboss/Qwen-Image-2.1-Outpaint-LoRA", "a8d173d22cb2a4ea325361af0e09020c73ca1e13", "qwen-image-2.1-outpaint-v2.safetensors", 159436576, "3611a5ccae5f790405eeacf1dfb2c89285c1e4f2987b9abc88cd0161a60eca28"),
    "restore": ("ausboss/Qwen-Image-2.1-Restore-LoRA", "30cb947f5b9c6682a85f8d31017be4807c459682", "qwen-image-2.1-restore.safetensors", 159436584, "65de4f6c2468071d5aa6ffbd82c76bfee7cc8ac28fe960e91bbca4a58f43c08c"),
    "head": ("Alissonerdx/BFS-Best-Face-Swap", "0ca3913ade4b4ada458d60c232354e8586c4c181", "bfs_head_v1.1_qwen_2.1.safetensors", 260096144, "d1d748d5601077f3b6d05766f6823510e901970d916afa404a97e85dc92fa88e"),
    "body": ("Alissonerdx/BFS-Best-Face-Swap", "0ca3913ade4b4ada458d60c232354e8586c4c181", "bfs_body_swap_v1.0_qwen_2.1.safetensors", 209753576, "7dc0a53aba4dbc70c204f498936a619d226559da11011f748c389189af46b664"),
}


def png_bytes(image: Image.Image) -> bytes:
    result = io.BytesIO()
    image.save(result, format="PNG")
    return result.getvalue()


def decode_mask(value: str, size: tuple[int, int]) -> Image.Image:
    if not value.startswith("data:image/png;base64,"):
        raise ValueError("A mascara deve ser uma imagem PNG.")
    raw = base64.b64decode(value.split(",", 1)[1], validate=True)
    with Image.open(io.BytesIO(raw)) as opened:
        if opened.width * opened.height > 16_777_216:
            raise ValueError("Mascara excede o tamanho permitido.")
        mask = opened.convert("L").resize(size, Image.Resampling.NEAREST)
    if not mask.getbbox():
        raise ValueError("Selecione a area que deseja editar.")
    return mask


def validate_mode_references(mode, references):
    if mode == "restore" and len(references) != 1:
        raise ValueError("Selecione apenas uma imagem para restaurar.")
    if mode in {"inpaint", "outpaint"} and len(references) != 1:
        raise ValueError("Selecione apenas uma imagem para editar.")
    if mode == "body" and not 2 <= len(references) <= 4:
        raise ValueError("Use de duas a quatro imagens, incluindo a base.")
    if mode == "outfit" and not 2 <= len(references) <= 5:
        raise ValueError("Use de duas a cinco imagens, incluindo a base.")


class NeveImage2ModeRuntime(fast.NeveImage2SRuntime):
    def __init__(self, options: ImageModeOptions):
        super().__init__()
        self._verified_assets = _VERIFIED_MODE_ASSETS
        self.options = options
        self.original = None
        self.mask = None
        self.box = None
        self.final_size = None
        self._mask_path = None

    async def _models(self, progress):
        await super()._models(progress)
        asset = ASSETS.get(self.options.mode)
        if not asset:
            return
        from huggingface_hub import hf_hub_download
        repo, revision, name, size, digest = asset
        directory = fast.MODELS_DIR / "loras" / "neve_modes"
        path = directory / name
        if not path.is_file() or path.stat().st_size != size:
            await asyncio.to_thread(hf_hub_download, repo_id=repo, revision=revision,
                                    filename=name, local_dir=str(directory))
        stat = path.stat()
        signature = stat.st_size, stat.st_mtime_ns
        if self._verified_assets.get(path) != signature:
            if stat.st_size != size or await asyncio.to_thread(fast._sha256, path) != digest:
                raise RuntimeError("LoRA do modo de imagem invalida: " + name)
            self._verified_assets[path] = signature

    def _encode_reference(self, raw, index, count, *, cpu_mode=False):
        with Image.open(io.BytesIO(raw)) as opened:
            image = ImageOps.exif_transpose(opened).convert("RGB")
        if index:
            rect = self.options.reference_crops[index - 1] if index <= len(self.options.reference_crops) else None
            if rect:
                x, y, w, h = rect
                if not (0 <= x < 1 and 0 <= y < 1 and 0 < w <= 1 - x and 0 < h <= 1 - y):
                    raise ValueError("Recorte de referencia invalido.")
                image = image.crop((round(x * image.width), round(y * image.height), round((x + w) * image.width), round((y + h) * image.height)))
                raw = png_bytes(image)
            return super()._encode_reference(raw, index, count, cpu_mode=cpu_mode)
        o = self.options
        if o.crop:
            x, y, w, h = o.crop
            if not (0 <= x < 1 and 0 <= y < 1 and 0 < w <= 1 - x and 0 < h <= 1 - y):
                raise ValueError("Recorte invalido.")
            image = image.crop((round(x * image.width), round(y * image.height),
                                round((x + w) * image.width), round((y + h) * image.height)))
        self.original = image
        self.final_size = image.size
        if o.mode == "outpaint":
            alpha = image.convert("RGBA").rotate(o.rotation, Image.Resampling.BICUBIC, expand=True)
            left, top = round(image.width * o.pad_left / 100), round(image.height * o.pad_top / 100)
            width = alpha.width + left + round(image.width * o.pad_right / 100)
            height = alpha.height + top + round(image.height * o.pad_bottom / 100)
            if width * height > 16_777_216:
                raise ValueError("A tela expandida excede 16 MP.")
            canvas = Image.new("RGB", (width, height), "#808080")
            canvas.paste(alpha, (left, top), alpha.getchannel("A"))
            keep = Image.new("L", canvas.size, 0)
            keep.paste(alpha.getchannel("A"), (left, top))
            self.original, self.mask = canvas.copy(), ImageOps.invert(keep)
            self.final_size = canvas.size
            image = canvas
        elif o.mode == "inpaint":
            self.mask = decode_mask(o.mask or "", self.original.size)
            if o.grow:
                self.mask = self.mask.filter(ImageFilter.MaxFilter(o.grow * 2 + 1))
            bounds = self.mask.getbbox()
            margin = max(32, o.feather * 3, round(max(bounds[2] - bounds[0], bounds[3] - bounds[1]) * 0.3))
            self.box = (max(0, bounds[0] - margin), max(0, bounds[1] - margin),
                        min(image.width, bounds[2] + margin), min(image.height, bounds[3] + margin))
            image = image.crop(self.box)
        # Separate mode resolution policy; the normal encoder is not modified.
        pixels = 1_500_000 if o.mode == "inpaint" else 1_327_104
        scale = min(math.sqrt(pixels / (image.width * image.height)), 2048 / max(image.size))
        size = tuple(max(32, round(side * scale / 32) * 32) for side in image.size)
        if cpu_mode:
            from neveai.utils.image_memory import cpu_image_size
            size = cpu_image_size(*size)
        return png_bytes(image.resize(size, Image.Resampling.LANCZOS)), size

    def _output_dimensions(self, width, height):
        size = self.final_size or (width, height)
        size = tuple(side * self.options.upscale for side in size)
        if size[0] * size[1] > 16_777_216 or max(size) > 8192:
            raise ValueError("O resultado excede 16 MP ou 8192 pixels por lado.")
        return size

    def _finalize_image(self, data):
        if self.original is None:
            return data
        with Image.open(io.BytesIO(data)) as opened:
            image = opened.convert("RGB")
        if self.options.mode == "inpaint":
            patch = image.resize((self.box[2] - self.box[0], self.box[3] - self.box[1]), Image.Resampling.LANCZOS)
            mask = self.mask.crop(self.box)
            if self.options.feather:
                mask = mask.filter(ImageFilter.GaussianBlur(self.options.feather))
            result = self.original.copy()
            result.paste(patch, self.box[:2], mask)
        elif self.options.mode == "outpaint":
            result = image.resize(self.original.size, Image.Resampling.LANCZOS)
            keep = ImageOps.invert(self.mask)
            if self.options.feather:
                # Feather inward only; pixels well inside the original remain exact.
                keep = keep.filter(ImageFilter.MinFilter(self.options.feather * 2 + 1)).filter(ImageFilter.GaussianBlur(self.options.feather / 2))
            result.paste(self.original, (0, 0), keep)
        else:
            result = image.resize(self.original.size, Image.Resampling.LANCZOS)
        return png_bytes(result)

    def build_workflow(self, prompt, width, height, refs, seed):
        o = self.options
        validate_mode_references(o.mode, refs)
        if not refs and o.mode != "auto":
            raise ValueError("Adicione a imagem principal para usar este modo.")
        if o.mode in {"outfit", "head", "body"} and len(refs) < 2:
            raise ValueError("Este modo precisa da imagem principal e de uma referencia.")
        if o.mode == "outpaint":
            prompt = "Outpaint the image: replace the solid gray areas with a seamless continuation of the scene, keeping the existing picture unchanged. " + prompt
        elif o.mode == "restore":
            prompt = "Restore the photo: remove blur, noise and compression artifacts and recover sharp, natural detail, keeping the same composition, people and colors. " + prompt
        elif o.mode == "outfit":
            labels = "; ".join(f"image {i + 2}: {label[:160]}" for i, label in enumerate(o.reference_labels) if label.strip())
            prompt = f"Dress {o.target} in image 1 in the clothes shown in the other images. {labels}. Keep their face, hair, hands, pose and background exactly the same. User instructions: {prompt}"
        elif o.mode in {"head", "body"}:
            task = "head_swap" if o.mode == "head" else "body_swap"
            prompt = f"{task}: Start with <image1> as the base. Replace the {('head' if o.mode == 'head' else 'whole person')} of {o.target} with the {('head' if o.mode == 'head' else 'person and outfit')} from <image2>. Preserve the pose, lighting, environment and background of <image1>. {prompt}"
            if o.mode == "body" and len(refs) > 2:
                prompt += " Use " + ", ".join(f"<image{i}>" for i in range(3, len(refs) + 1)) + " as additional character references according to the user instructions."
        graph = super().build_workflow(prompt, width, height, refs, seed)
        if o.mode == "inpaint":
            if self.mask is None or self.box is None:
                raise ValueError("Selecione a area que deseja editar.")
            self._mask_path = fast.INPUT_DIR / f"neve_mode_mask_{uuid4().hex}.png"
            self._mask_path.write_bytes(png_bytes(self.mask.crop(self.box).resize((width, height), Image.Resampling.LANCZOS)))
            graph["30"] = {"class_type": "LoadImageMask", "inputs": {"image": self._mask_path.name, "channel": "red"}}
            graph["32"] = {"class_type": "VAEEncode", "inputs": {"pixels": ["15", 0], "vae": ["4", 0]}}
            graph["31"] = {"class_type": "SetLatentNoiseMask", "inputs": {"samples": ["32", 0], "mask": ["30", 0]}}
            graph["11"]["inputs"]["latent_image"] = ["31", 0]
        if o.auto_prompt:
            batch = None
            for index in range(len(refs)):
                padded = str(90 + index)
                graph[padded] = {"class_type": "ResizeAndPadImage", "inputs": {
                    "image": [str(15 + index), 0], "target_width": 768, "target_height": 768,
                    "padding_color": "black", "interpolation": "lanczos",
                }}
                if batch is None:
                    batch = [padded, 0]
                else:
                    node = str(80 + index)
                    graph[node] = {"class_type": "ImageBatch", "inputs": {"image1": batch, "image2": [padded, 0]}}
                    batch = [node, 0]
            graph["70"] = {"class_type": "TextGenerate", "inputs": {
                "clip": ["3", 0], **({"image": batch} if refs else {}), "prompt": "Write only a precise English instruction for this image generation or editing request. Preserve every explicit constraint and image number; do not invent additional changes. Request: " + prompt,
                "max_length": 256, "sampling_mode": "off", "thinking": False,
                "use_default_template": True, "mtp": "off",
            }}
            graph["5"]["inputs"]["prompt"] = ["70", 0]
        asset = ASSETS.get(o.mode)
        if asset:
            graph["60"] = {"class_type": "LoraLoaderModelOnly", "inputs": {
                "model": ["1", 0], "lora_name": str(Path("neve_modes") / asset[2]), "strength_model": o.strength,
            }}
            graph["2"]["inputs"]["model"] = ["60", 0]
            if o.mode in {"outfit", "restore"}:
                # The author's Turbo recipe uses seven LoRA steps and one plain step.
                graph["10"]["inputs"]["sigmas"] = fast.SIGMAS.rsplit(",", 1)[0]
                graph["61"] = {"class_type": "BasicGuider", "inputs": {"model": ["1", 0], "conditioning": ["5", 0]}}
                graph["62"] = {"class_type": "ManualSigmas", "inputs": {"sigmas": "0.414568, 0"}}
                graph["63"] = {"class_type": "DisableNoise", "inputs": {}}
                graph["64"] = {"class_type": "SamplerCustomAdvanced", "inputs": {
                    "noise": ["63", 0], "guider": ["61", 0], "sampler": ["9", 0],
                    "sigmas": ["62", 0], "latent_image": ["11", 0],
                }}
                graph["12"]["inputs"]["samples"] = ["64", 0]
        return graph

    async def _run_once(self, *args, **kwargs):
        import httpx
        try:
            return await super()._run_once(*args, **kwargs)
        except httpx.HTTPStatusError as exc:
            raise RuntimeError("Workflow de edicao: " + exc.response.text[:4000]) from exc
        finally:
            if self._mask_path is not None:
                self._mask_path.unlink(missing_ok=True)
                self._mask_path = None


async def run_image_mode(*, options, **kwargs):
    parsed = ImageModeOptions.model_validate(options)
    if parsed.mode == "normal":
        return await fast.neve_image_2s_runtime.run(**kwargs)
    async with _MODE_LOCK:
        return await _run_image_mode(parsed, kwargs)


async def _run_image_mode(parsed, kwargs):
    validate_mode_references(parsed.mode, kwargs.get("references") or [])
    from neveai.routers.stable_diffusion import _preferred_sd_cpp_windows_backend
    if await asyncio.to_thread(_preferred_sd_cpp_windows_backend) == "vulkan":
        raise ValueError("Os modos especiais precisam do runtime ComfyUI; o caminho AMD Vulkan continua disponivel no modo Normal.")
    runtime = NeveImage2ModeRuntime(parsed)
    if parsed.upscale == 1:
        return await runtime.run(**kwargs)
    progress = kwargs["progress"]
    if not kwargs.get("references") and kwargs.get("dimensions"):
        dimensions = kwargs["dimensions"]
        async def enlarged_dimensions(width, height):
            await dimensions(width * 2, height * 2)
        kwargs = {**kwargs, "dimensions": enlarged_dimensions}
    kwargs = {**kwargs, "progress": lambda value: progress(round(value * 0.75))}
    result = await runtime.run(**kwargs)
    with Image.open(io.BytesIO(base64.b64decode(result.split(",", 1)[1]))) as opened:
        source = opened.convert("RGB")
    size = tuple(side * 2 for side in source.size)
    if size[0] * size[1] > 16_777_216 or max(size) > 8192:
        raise ValueError("A ampliacao excede 16 MP ou 8192 pixels por lado.")
    enlarged = source.resize(size, Image.Resampling.LANCZOS)
    tile_size, overlap = 1024, 96
    positions = lambda side: list(dict.fromkeys([min(p, max(0, side - tile_size)) for p in range(0, side, tile_size - overlap)]))
    tiles = [(x, y, min(size[0], x + tile_size), min(size[1], y + tile_size)) for y in positions(size[1]) for x in positions(size[0])]
    import numpy as np
    total = np.zeros((size[1], size[0], 3), dtype=np.float32)
    weights = np.zeros((size[1], size[0]), dtype=np.float32)
    for index, box in enumerate(tiles):
        crop = enlarged.crop(box)
        reference = "data:image/png;base64," + base64.b64encode(png_bytes(crop)).decode("ascii")
        tile = NeveImage2ModeRuntime(ImageModeOptions(mode="restore", strength=0.5))
        tile_result = await tile.run(
            prompt="Restore natural fine detail. Preserve exactly the subjects, colors, composition and any lettering.",
            resolution="1:1", references=[reference], user_id=kwargs.get("user_id"),
            progress=lambda value, index=index: progress(75 + round(24 * (index + value / 100) / len(tiles))),
        )
        with Image.open(io.BytesIO(base64.b64decode(tile_result.split(",", 1)[1]))) as opened:
            image = opened.convert("RGB").resize(crop.size, Image.Resampling.LANCZOS)
        h, w = crop.height, crop.width
        wx, wy = np.ones(w, dtype=np.float32), np.ones(h, dtype=np.float32)
        ramp = np.linspace(0.01, 1, min(overlap, w, h), dtype=np.float32)
        if box[0]: wx[:len(ramp)] = ramp
        if box[2] < size[0]: wx[-len(ramp):] = ramp[::-1]
        if box[1]: wy[:len(ramp)] = ramp
        if box[3] < size[1]: wy[-len(ramp):] = ramp[::-1]
        weight = wy[:, None] * wx[None, :]
        total[box[1]:box[3], box[0]:box[2]] += np.asarray(image, dtype=np.float32) * weight[:, :, None]
        weights[box[1]:box[3], box[0]:box[2]] += weight
    output = Image.fromarray(np.clip(total / np.maximum(weights[:, :, None], 1e-6), 0, 255).astype("uint8"))
    return "data:image/png;base64," + base64.b64encode(png_bytes(output)).decode("ascii")


def initial_mode_dimensions(options, references, user_id, resolution="1:1"):
    from neveai.routers.stable_diffusion import _read_image_reference_bytes
    parsed = ImageModeOptions.model_validate(options)
    validate_mode_references(parsed.mode, references)
    if not references:
        if parsed.mode == "auto":
            return NeveImage2ModeRuntime(parsed)._output_dimensions(*fast.DIMENSIONS.get(resolution, fast.DIMENSIONS["1:1"]))
        raise ValueError("Adicione a imagem principal para usar este modo.")
    if parsed.mode in {"outfit", "head", "body"} and len(references) < 2:
        raise ValueError("Este modo precisa de duas imagens.")
    runtime = NeveImage2ModeRuntime(parsed)
    runtime._encode_reference(_read_image_reference_bytes(references[0], user_id), 0, len(references))
    return runtime._output_dimensions(*runtime.final_size)


class SegmentPoint(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)


class SegmentRequest(BaseModel):
    image: str = Field(max_length=24_000_000)
    positive: list[SegmentPoint] = Field(default_factory=list, max_length=64)
    negative: list[SegmentPoint] = Field(default_factory=list, max_length=64)
    prepare: bool = False

    @model_validator(mode="after")
    def requires_positive_click(self):
        if not self.prepare and not self.positive:
            raise ValueError("Selecione um ponto na imagem.")
        return self

async def segment_image(form: SegmentRequest, user_id):
    from neveai.routers.stable_diffusion import _read_image_reference_bytes
    from neveai.routers.image_mode_selection import click_selector
    raw = await asyncio.to_thread(_read_image_reference_bytes, form.image, user_id)
    return await asyncio.to_thread(click_selector.select, raw, form.positive, form.negative, user_id, prepare=form.prepare)
