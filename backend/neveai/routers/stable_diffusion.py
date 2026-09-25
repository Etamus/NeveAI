"""Geracao local de imagens Z-Image-Turbo e Qwen Image via stable-diffusion.cpp."""

import asyncio
import base64
import fnmatch
import hashlib
import io
import json
import logging
import os
import random
import re
import shutil
import subprocess
import time
import unicodedata
import urllib.parse
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Awaitable, Callable, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from neveai.config import CACHE_DIR, STABLE_DIFFUSION_HF_TOKEN
from neveai.constants import ERROR_MESSAGES
from neveai.utils.access_control import has_permission
from neveai.utils.auth import get_admin_user, get_verified_user

log = logging.getLogger(__name__)
router = APIRouter()

ImageProgressCallback = Callable[[int], Awaitable[None]]
ImageDimensionsCallback = Callable[[int, int], Awaitable[None]]

BACKEND_DIR = Path(__file__).resolve().parents[2]
SD_CPP_DIR = BACKEND_DIR / "bin" / "stable-diffusion-cpp"
SD_CLI_PATH = SD_CPP_DIR / ("sd-cli.exe" if os.name == "nt" else "sd-cli")
SD_CPP_RELEASE_API = "https://api.github.com/repos/leejet/stable-diffusion.cpp/releases/latest"
SD_CPP_WIN_CUDA_ASSET = "sd-*-bin-win-cuda12-x64.zip"
SD_CPP_WIN_CUDART_ASSET = "cudart-sd-bin-win-cu12-x64.zip"
SD_CPP_WIN_VULKAN_ASSET = "sd-*-bin-win-vulkan-x64.zip"
SD_CPP_WIN_CPU_ASSET = "sd-*-bin-win-cpu-x64.zip"
SD_CLI_TIMEOUT_SECONDS = 60 * 60
SD_CPP_QWEN_IMAGE_21_MIN_BUILD = 899

IMAGE_OUTPUT_DIR = CACHE_DIR / "image" / "generations"
IMAGE_INPUT_DIR = CACHE_DIR / "image" / "inputs"
IMAGE_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
IMAGE_INPUT_DIR.mkdir(parents=True, exist_ok=True)

SD_CACHE_DIR = CACHE_DIR / "stable_diffusion"
GGUF_CACHE_DIR = SD_CACHE_DIR / "gguf"
QWEN3_CACHE_DIR = SD_CACHE_DIR / "qwen3"
VAE_CACHE_DIR = SD_CACHE_DIR / "vae"
MAGEFLOW_CACHE_DIR = SD_CACHE_DIR / "mageflow"
LORA_CACHE_DIR = SD_CACHE_DIR / "loras"
PROMPT_TRANSLATOR_CACHE_DIR = SD_CACHE_DIR / "prompt_translator"
GGUF_CACHE_DIR.mkdir(parents=True, exist_ok=True)
QWEN3_CACHE_DIR.mkdir(parents=True, exist_ok=True)
VAE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
MAGEFLOW_CACHE_DIR.mkdir(parents=True, exist_ok=True)
LORA_CACHE_DIR.mkdir(parents=True, exist_ok=True)
PROMPT_TRANSLATOR_CACHE_DIR.mkdir(parents=True, exist_ok=True)

ZIMAGE_REPO = "leejet/Z-Image-Turbo-GGUF"
ZIMAGE_GGUF_FILE = "z_image_turbo-Q4_0.gguf"
ZIMAGE_QUALITY_REPO = ZIMAGE_REPO
ZIMAGE_QUALITY_GGUF_FILE = "z_image_turbo-Q8_0.gguf"
QWEN3_LLM_REPO = "unsloth/Qwen3-4B-Instruct-2507-GGUF"
QWEN3_LLM_FILE = "Qwen3-4B-Instruct-2507-Q4_K_M.gguf"
ZIMAGE_UNCENSORED_LLM_REPO = "BennyDaBall/Qwen3-4b-Z-Image-Turbo-AbliteratedV1"
ZIMAGE_UNCENSORED_LLM_FILE = "Z-Image-AbliteratedV1.Q4_K_M.gguf"
QWEN_IMAGE_21_REPO = "abenzerps/Qwen-Image-2.1-Uncensored-GGUF"
QWEN_IMAGE_21_FILE = "qwen-image-2.1-UC-Q6_K.gguf"
QWEN_IMAGE_21_LLM_REPO = "mradermacher/Qwen3-VL-8B-Instruct-Heretic-GGUF"
QWEN_IMAGE_21_LLM_FILE = "Qwen3-VL-8B-Instruct-heretic.Q4_K_M.gguf"
QWEN_IMAGE_21_VISION_FILE = "Qwen3-VL-8B-Instruct-heretic.mmproj-Q8_0.gguf"
QWEN_IMAGE_21_VAE_REPO = "Comfy-Org/Qwen-Image-2.1"
QWEN_IMAGE_21_VAE_FILE = "vae/qwen_image_2.1_vae_bf16.safetensors"
PROMPT_TRANSLATOR_REPO = "mradermacher/Huihui-Qwen3-4B-Instruct-2507-abliterated-GGUF"
PROMPT_TRANSLATOR_FILE = "Huihui-Qwen3-4B-Instruct-2507-abliterated.Q4_K_M.gguf"
ZIMAGE_VAE_REPO = "Comfy-Org/z_image_turbo"
ZIMAGE_VAE_FILE = "split_files/vae/ae.safetensors"
MAGEFLOW_REPO = "gguf-org/mageflow-gguf"
MAGEFLOW_EDIT_FILE = "mageflow-edit-turbo-nvfp4.gguf"
MAGEFLOW_VAE_FILE = "pig_mageflow_vae_fp32-f16.gguf"
MAGEFLOW_LLM_REPO = "mradermacher/Qwen3-VL-4B-Instruct-Heretic-GGUF"
MAGEFLOW_LLM_FILE = "Qwen3-VL-4B-Instruct-heretic.Q4_K_M.gguf"
MAGEFLOW_VISION_FILE = "Qwen3-VL-4B-Instruct-heretic.mmproj-f16.gguf"

MAX_IMAGE_WIDTH = 768
MAX_IMAGE_HEIGHT = 768
MAX_IMAGE_STEPS = 8
QUALITY_IMAGE_WIDTH = 1280
QUALITY_IMAGE_HEIGHT = 1280
QUALITY_IMAGE_STEPS = 8
QUALITY_IMAGE_RESOLUTIONS = {
    "1:1": (1024, 1024),
    "16:9": (1280, 720),
    "9:16": (720, 1280),
    "4:3": (1152, 864),
    "3:4": (864, 1152),
}
QWEN_IMAGE_21_STEPS = 25
QWEN_IMAGE_21_CFG_SCALE = 6.0
QWEN_IMAGE_21_MAX_REFERENCES = 10
QWEN_IMAGE_21_FULL_GPU_MIN_VRAM_MIB = 14 * 1024
QWEN_IMAGE_21_RESOLUTIONS = {
    "1:1": (1152, 1152),
    "16:9": (1216, 704),
    "9:16": (704, 1216),
    "4:3": (1152, 864),
    "3:4": (864, 1152),
}
DEFAULT_CFG_SCALE = 1.0
DEFAULT_IMG2IMG_STRENGTH = 0.55
MAX_INIT_IMAGE_BYTES = 30 * 1024 * 1024
IMAGE_PROMPT_TRANSLATION_TIMEOUT_SECONDS = 60.0


@dataclass(frozen=True)
class _ZImageStyle:
    download_urls: tuple[str, ...]
    filename: str
    sha256: str
    weight: float
    prompt_prefix: str = ""


ZIMAGE_STYLE_SPECS = {
    "minimalist": _ZImageStyle(
        download_urls=(
            "https://huggingface.co/atMrMattV/Visione/resolve/main/models/styles/MinimalistVectorArtZ.safetensors?download=true",
            "https://civitai.com/api/download/models/2594513",
        ),
        filename="neve-minimalist.safetensors",
        sha256="14e6caed34e1a718c13f54617494db5e47fc5606815915f60e882d2518d6c221",
        weight=1.0,
        prompt_prefix="Minimalist Vector Art, ArsMJStyle",
    ),
    "polygonal": _ZImageStyle(
        download_urls=(
            "https://huggingface.co/alexrzem/zit-loras/resolve/main/turbo/3D_%26_Craft_-_Low_Poly_Papercraft_-_ZImageTurbo_-_bblink787.safetensors?download=true",
            "https://civitai.com/api/download/models/2474853?fileId=2363302",
        ),
        filename="neve-polygonal.safetensors",
        sha256="fc39e5bfa1a9b1b3d112e55d1b4c064ea67268f89622822759f16b93fdf6cd68",
        weight=0.8,
        prompt_prefix="vibrantly colored low poly papercraft scene, bold colors",
    ),
    "fantasy": _ZImageStyle(
        download_urls=(
            "https://huggingface.co/alexrzem/zit-loras/resolve/main/turbo/Art_Style_-_Dark_Fantasy_Armor_-_ZImageTurbo_-_Razane.safetensors?download=true",
            "https://civitai.com/api/download/models/2579449",
        ),
        filename="neve-fantasy.safetensors",
        sha256="f848c7866f1438a82cd72397c19dca429a9808542886e4b6e6c72adb116a5212",
        weight=1.0,
        prompt_prefix="raz'sdarkfantasystyle-zit-mk.1",
    ),
    "comics": _ZImageStyle(
        download_urls=(
            "https://huggingface.co/ThirdTimesTheCiarc/stylish/resolve/main/1764315/2961085/Comic%20Book%20V4T3_E10.safetensors?download=true",
            "https://civitai.com/api/download/models/2961085",
        ),
        filename="neve-comics.safetensors",
        sha256="33eef7470d18b25c578c235f27d118252e265e578f38b1e1f888222e89097182",
        weight=0.75,
        prompt_prefix="Bradhamel art style, comic book illustration",
    ),
    "spontaneous": _ZImageStyle(
        download_urls=(
            "https://civitai.com/api/download/models/2452071?fileId=2343134",
        ),
        filename="neve-spontaneous.safetensors",
        sha256="b77465f098a65455364d1118a0c2465091f38fa3ced7cfb64be7ac123ec0e773",
        weight=0.85,
        prompt_prefix="l3n0v0, candid analog photography",
    ),
    "realistic": _ZImageStyle(
        download_urls=(
            "https://huggingface.co/JExomgmt/Z-Image/resolve/main/RealisticSnapshot-Zimage-Turbov5.safetensors?download=true",
            "https://civitai.com/api/download/models/2617751?fileId=2505151",
        ),
        filename="neve-realistic.safetensors",
        sha256="182d7f92475b8d7f792203127738d31270403e86e007fdc7792d324a3406e556",
        weight=0.65,
        prompt_prefix="photorealistic candid snapshot",
    ),
    "arcane": _ZImageStyle(
        download_urls=(
            "https://huggingface.co/ThirdTimesTheCiarc/stylish/resolve/main/2337762/2629656/Studio%20Fortiche_E15.safetensors?download=true",
            "https://civitai.com/api/download/models/2629656?fileId=2517602",
        ),
        filename="neve-arcane-fortiche.safetensors",
        sha256="216ade991f3b1422dbfcd1a8d29b8d1e0818039ed46e5fba3ec167c855e0a8c7",
        weight=0.8,
        prompt_prefix="StudiFort art style",
    ),
    "manga": _ZImageStyle(
        download_urls=(
            "https://civitai.com/api/download/models/2577798?fileId=2465041",
        ),
        filename="neve-manga.safetensors",
        sha256="c5cf2e4ef21548e85ef718e7cae9d72fbdabcb02c72f7e7bb1c0e4bd124267ed",
        weight=0.9,
        prompt_prefix="black and white manga style",
    ),
    "pixelated": _ZImageStyle(
        download_urls=(
            "https://huggingface.co/camenduru/Z-Image-Loras/resolve/main/aziib_pixel_style_zit.safetensors?download=true",
            "https://civitai.com/api/download/models/2495486?fileId=2383838",
        ),
        filename="neve-pixelated.safetensors",
        sha256="33a98b2e10695d3d8bae76372bdaa1cd0bf3b3418d32a9614d83e2d2eab4af8d",
        weight=0.8,
        prompt_prefix="aziib_pixel_style, crisp pixel art",
    ),
}


def _cleanup_obsolete_style_loras() -> None:
    current_files = {spec.filename for spec in ZIMAGE_STYLE_SPECS.values()}
    for candidate in LORA_CACHE_DIR.iterdir():
        try:
            if candidate.is_dir():
                shutil.rmtree(candidate)
            elif candidate.name not in current_files:
                candidate.unlink(missing_ok=True)
        except Exception as exc:
            log.warning("Nao foi possivel limpar LoRA antigo %s: %s", candidate, exc)


_cleanup_obsolete_style_loras()


def normalize_image_style(value: Optional[str]) -> str:
    value = str(value or "none").strip().lower()
    return value if value in ZIMAGE_STYLE_SPECS else "none"


def normalize_image_quality(value: Optional[str]) -> str:
    value = str(value or "neve_image").strip().lower()
    return value if value in {"neve_image", "neve_image_2", "qwen_image_2_1", "qwen_image_2s"} else "neve_image"


def normalize_qwen_image_resolution(value: Optional[str]) -> str:
    value = str(value or "1:1").strip()
    return value if value in QWEN_IMAGE_21_RESOLUTIONS else "1:1"


def qwen_image_dimensions(value: Optional[str]) -> tuple[int, int]:
    return QWEN_IMAGE_21_RESOLUTIONS[normalize_qwen_image_resolution(value)]


def quality_image_dimensions(value: Optional[str]) -> tuple[int, int]:
    resolution = str(value or "1:1").strip()
    return QUALITY_IMAGE_RESOLUTIONS.get(resolution, QUALITY_IMAGE_RESOLUTIONS["1:1"])

_PORTUGUESE_MARKERS = {
    "quero", "gere", "gerar", "crie", "criar", "desenhe", "faça", "faca",
    "imagem", "foto", "retrato", "realista", "cinematografico", "cinematográfico",
    "com", "sem", "para", "sobre", "baixo", "alto", "dentro", "fora",
    "homem", "mulher", "menino", "menina", "pessoa", "cachorro", "gato",
    "cidade", "praia", "floresta", "montanha", "ceu", "céu", "noite", "dia",
    "rua", "câmera", "camera", "granulada", "granulado", "iluminacao", "iluminação",
    "vermelho", "azul", "verde", "amarelo", "preto", "branco", "luz",
    "um", "uma", "dois", "duas", "tres", "quatro", "personagem", "personagens",
    "guerra", "batalha", "paisagem", "cenario", "mulheres", "homens",
}
_ENGLISH_MARKERS = {
    "a", "the", "with", "and", "without", "photo", "photograph", "portrait",
    "image", "realistic", "cinematic", "woman", "man", "person", "camera",
    "flash", "grainy", "lighting", "street", "standing", "looking", "smile",
}
_PORTUGUESE_ACCENT_RE = re.compile(r"[áàâãéêíóôõúçÁÀÂÃÉÊÍÓÔÕÚÇ]")
_WORD_RE = re.compile(r"[a-zA-ZÀ-ÿ]+")
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?;])\s+")


def _clamp_int(value: Optional[int], default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(value) if value is not None else default
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(maximum, value))


def _align_image_dim(value: Optional[int], default: int, maximum: int) -> int:
    value = _clamp_int(value, default, 256, maximum)
    return max(256, (value // 16) * 16)


def _cfg_scale(value: Optional[float]) -> float:
    return DEFAULT_CFG_SCALE


def normalize_sd_model_id(model_id: Optional[str]) -> str:
    return ZIMAGE_REPO


@dataclass(frozen=True)
class _InitImage:
    path: Path
    width: int
    height: int


def _file_id_from_image_reference(reference: str) -> Optional[str]:
    reference = str(reference or "").strip()
    if not reference or reference.startswith("data:image/"):
        return None

    match = re.search(r"/files/([^/?#]+)(?:/content)?", reference)
    if match:
        return urllib.parse.unquote(match.group(1))

    if reference.startswith("http://") or reference.startswith("https://"):
        return None

    return reference


def _read_image_reference_bytes(reference: str, user_id: Optional[str] = None) -> bytes:
    reference = str(reference or "").strip()
    if not reference:
        raise RuntimeError("Referencia de imagem vazia")

    if reference.startswith("data:image/"):
        try:
            header, payload = reference.split(",", 1)
        except ValueError as e:
            raise RuntimeError("Data URI de imagem invalido") from e

        if ";base64" in header:
            raw = base64.b64decode(payload, validate=True)
        else:
            raw = urllib.parse.unquote_to_bytes(payload)
    else:
        file_id = _file_id_from_image_reference(reference)
        if file_id:
            from neveai.models.files import Files
            from neveai.storage.provider import Storage

            file = Files.get_file_by_id_and_user_id(file_id, user_id) if user_id else Files.get_file_by_id(file_id)
            if not file:
                raise RuntimeError("Imagem anexada nao encontrada ou sem permissao")

            content_type = str((file.meta or {}).get("content_type") or "")
            if content_type and not content_type.startswith("image/"):
                raise RuntimeError("Arquivo anexado nao e uma imagem")

            file_path = Path(Storage.get_file(file.path))
            if not file_path.is_file():
                raise RuntimeError("Arquivo de imagem anexado nao existe no armazenamento")
            raw = file_path.read_bytes()
        elif reference.startswith("http://") or reference.startswith("https://"):
            request = urllib.request.Request(reference, headers={"User-Agent": "NeveAI/1.0"})
            with urllib.request.urlopen(request, timeout=60) as response:
                content_type = response.headers.get("Content-Type", "")
                if content_type and not content_type.startswith("image/"):
                    raise RuntimeError("URL anexada nao retornou uma imagem")
                raw = response.read(MAX_INIT_IMAGE_BYTES + 1)
        else:
            raise RuntimeError("Referencia de imagem anexada nao suportada")

    if len(raw) > MAX_INIT_IMAGE_BYTES:
        raise RuntimeError("Imagem anexada excede o limite de 30 MB para img2img")
    if not raw:
        raise RuntimeError("Imagem anexada esta vazia")
    return raw


def _prepare_init_image_sync(reference: str, user_id: Optional[str] = None) -> _InitImage:
    from PIL import Image, ImageOps

    raw = _read_image_reference_bytes(reference, user_id=user_id)
    try:
        image = Image.open(io.BytesIO(raw))
        image = ImageOps.exif_transpose(image)
        image.seek(0)
        image = image.convert("RGB")
    except Exception as e:
        raise RuntimeError(f"Nao foi possivel ler a imagem anexada: {e}") from e

    output_path = IMAGE_INPUT_DIR / f"init_{int(time.time())}_{random.randint(0, 2**31 - 1)}.png"
    image.save(output_path, "PNG", optimize=True)
    return _InitImage(path=output_path, width=image.width, height=image.height)


async def _prepare_init_image(reference: Optional[str], user_id: Optional[str] = None) -> Optional[_InitImage]:
    reference = str(reference or "").strip()
    if not reference:
        return None

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _prepare_init_image_sync, reference, user_id)


async def _prepare_reference_images(
    references: Optional[list[str]], user_id: Optional[str] = None
) -> list[_InitImage]:
    unique_references: list[str] = []
    seen: set[str] = set()
    for reference in references or []:
        normalized = str(reference or "").strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        unique_references.append(normalized)
        if len(unique_references) >= QWEN_IMAGE_21_MAX_REFERENCES:
            break

    prepared: list[_InitImage] = []
    try:
        for reference in unique_references:
            image = await _prepare_init_image(reference, user_id=user_id)
            if image is not None:
                prepared.append(image)
        return prepared
    except BaseException:
        for image in prepared:
            image.path.unlink(missing_ok=True)
        raise


def _fit_init_image_dimensions(init_image: _InitImage, max_width: int, max_height: int, max_size: int = MAX_IMAGE_WIDTH) -> tuple[int, int]:
    max_width = _align_image_dim(max_width, max_size, max_size)
    max_height = _align_image_dim(max_height, max_size, max_size)

    if init_image.width <= 0 or init_image.height <= 0:
        return max_width, max_height

    scale = min(max_width / init_image.width, max_height / init_image.height)
    width = int(init_image.width * scale)
    height = int(init_image.height * scale)
    width = max(256, min(max_width, (width // 16) * 16))
    height = max(256, min(max_height, (height // 16) * 16))
    return width, height


def _looks_portuguese(text: str) -> bool:
    folded = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    words = {word.lower() for word in re.findall(r"[A-Za-z]+", folded)}
    return sum(1 for word in words if word in _PORTUGUESE_MARKERS) >= 2


def _looks_english(text: str) -> bool:
    if _PORTUGUESE_ACCENT_RE.search(text):
        return False
    words = {word.lower() for word in _WORD_RE.findall(text)}
    english_score = sum(1 for word in words if word in _ENGLISH_MARKERS)
    return english_score >= 2 and not _looks_portuguese(text)


def _normalize_image_prompt_text(prompt: str) -> str:
    return re.sub(r"\s+", " ", str(prompt or "")).strip()


def _short_log_prompt(prompt: str, limit: int = 500) -> str:
    prompt = _normalize_image_prompt_text(prompt)
    return prompt if len(prompt) <= limit else f"{prompt[:limit]}..."


def _contains_source_term(source_prompt: str, pattern: str) -> bool:
    return bool(re.search(pattern, source_prompt, flags=re.IGNORECASE))


def _source_photograph_opening(source_prompt: str) -> Optional[str]:
    source_prompt = _normalize_image_prompt_text(source_prompt)
    first_sentence = _SENTENCE_SPLIT_RE.split(source_prompt, maxsplit=1)[0]
    if not re.search(r"\b(fotografia|foto|retrato)\b", first_sentence, flags=re.IGNORECASE):
        return None

    lower = first_sentence.lower()
    if "preto e branco" in lower or "preta e branca" in lower or "p&b" in lower:
        prefix = "Black and white"
    elif re.search(r"\bcolorid[ao]s?\b|\bem cores\b", lower):
        prefix = "Color"
    else:
        prefix = ""

    medium_parts = []
    if re.search(r"\banal[oó]gic[ao]s?\b", lower):
        medium_parts.append("analog")
    elif re.search(r"\bdigit(?:al|ais)\b", lower):
        medium_parts.append("digital")

    medium_parts.append("photograph")
    opening = " ".join(part for part in [prefix, *medium_parts] if part).strip()
    if not opening:
        opening = "Photograph"

    descriptors = []
    if re.search(r"\bgranulad[ao]s?\b", lower):
        grain = "grainy"
        if re.search(r"\b(levemente|ligeiramente|suavemente|um pouco)\b", lower):
            grain = "slightly grainy"
        descriptors.append(grain)
    if re.search(r"\balto contraste\b|\bcontraste alto\b", lower):
        if descriptors:
            descriptors[-1] = f"{descriptors[-1]} with high contrast"
        else:
            descriptors.append("with high contrast")

    if descriptors:
        opening = f"{opening}, {', '.join(descriptors)}"
    return opening


def _restore_source_photograph_opening(prompt: str, source_prompt: str) -> str:
    opening = _source_photograph_opening(source_prompt)
    if not opening:
        return prompt

    starts_like_photo_prompt = re.match(
        r"^\s*(?:a\s+)?(?:colorful|colou?r|black\s+and\s+white|analog|analogue|digital|photo|photograph|photography)\b",
        prompt,
        flags=re.IGNORECASE,
    )
    if not starts_like_photo_prompt:
        return prompt

    if "." in prompt:
        return re.sub(r"^.*?\.", f"{opening}.", prompt, count=1)

    return re.sub(
        r"^\s*(?:a\s+)?(?:colorful,?\s*)?(?:(?:slightly|lightly)\s+grainy\s+)?(?:(?:analog|analogue|digital)\s+)?(?:colou?r\s+)?(?:photo(?:graph)?|photography)(?:\s+(?:with|and)\s+high\s+contrast)?",
        opening,
        prompt,
        count=1,
        flags=re.IGNORECASE,
    )


def _polish_translated_image_prompt(prompt: str, source_prompt: str = "") -> str:
    prompt = _normalize_image_prompt_text(prompt)
    prompt = _restore_source_photograph_opening(prompt, source_prompt)
    replacements = [
        (
            r"\bColorful\s+(analog|analogue|digital)\s+photography\b",
            lambda match: f"Color {'analog' if match.group(1).lower() == 'analogue' else match.group(1).lower()} photograph",
        ),
        (
            r"\bColor\s+(analog|analogue|digital)\s+photography\b",
            lambda match: f"Color {'analog' if match.group(1).lower() == 'analogue' else match.group(1).lower()} photograph",
        ),
        (
            r"\b(analog|analogue|digital)\s+color\s+photography\b",
            lambda match: f"color {'analog' if match.group(1).lower() == 'analogue' else match.group(1).lower()} photograph",
        ),
        (r"\bColorful\s+photography\b", "Color photograph"),
        (r"\bColor\s+photography\b", "Color photograph"),
        (r"\banalogue\b", "analog"),
        (r"\bface\s+paint(?:ing)?\b", "facepaint"),
    ]
    for pattern, replacement in replacements:
        prompt = re.sub(pattern, replacement, prompt, flags=re.IGNORECASE)

    if _contains_source_term(source_prompt, r"\bgola\s+alta\b"):
        prompt = re.sub(
            r"\b(trench coat|overcoat|coat|jacket) with turtleneck\b",
            r"\1 with high collar",
            prompt,
            flags=re.IGNORECASE,
        )
        prompt = re.sub(
            r"\bturtleneck sweater\b",
            "high neck sweater",
            prompt,
            flags=re.IGNORECASE,
        )

    if _contains_source_term(source_prompt, r"\breluzent[ees]*\b") and not re.search(
        r"\b(glowing|shining|sparkling|luminous)\b", prompt, flags=re.IGNORECASE
    ):
        prompt = re.sub(
            r"\bbright\s+(blue|green|red|gold(?:en)?|yellow|amber|purple|violet|white|black|gr[ae]y|orange|pink|brown)\s+eyes\b",
            r"bright \1 glowing eyes",
            prompt,
            flags=re.IGNORECASE,
        )
        prompt = re.sub(
            r"\b(blue|green|red|gold(?:en)?|yellow|amber|purple|violet|white|black|gr[ae]y|orange|pink|brown)\s+eyes\b",
            r"\1 glowing eyes",
            prompt,
            flags=re.IGNORECASE,
        )

    if _contains_source_term(source_prompt, r"\b[eé]lfic"):
        prompt = re.sub(r"\belven\s+ears\b", "elf ears", prompt, flags=re.IGNORECASE)

    if _contains_source_term(source_prompt, r"\bobservador\b"):
        prompt = re.sub(r"\blooking at the observer\b", "looking at the viewer", prompt, flags=re.IGNORECASE)
        prompt = re.sub(r"\blooking at viewer\b", "looking at the viewer", prompt, flags=re.IGNORECASE)

    if _contains_source_term(source_prompt, r"\bdeitad[ao]s?\s+de\s+costas\b"):
        pronoun = "their"
        if _contains_source_term(source_prompt, r"\bela\b"):
            pronoun = "her"
        elif _contains_source_term(source_prompt, r"\bele\b"):
            pronoun = "his"
        prompt = re.sub(r"\blying on your back\b", f"lying on {pronoun} back", prompt, flags=re.IGNORECASE)

    prompt = re.sub(r"\s+([,.])", r"\1", prompt)
    prompt = re.sub(r"\s+", " ", prompt).strip()
    return prompt


def _image_prompt_llama_cli() -> Optional[Path]:
    names = ("llama-cli.exe", "llama-cli") if os.name == "nt" else ("llama-cli",)
    roots = (
        BACKEND_DIR.parent / "llamacpp-server" / "bin",
        BACKEND_DIR / "bin" / "llama.cpp",
        BACKEND_DIR / "bin",
    )
    for root in roots:
        for name in names:
            candidate = root / name
            if candidate.is_file():
                return candidate
    return None


def _translate_image_prompt_locally_sync(prompt: str, llm_path: Path) -> str:
    llama_cli = _image_prompt_llama_cli()
    if llama_cli is None or not llm_path.is_file():
        return prompt
    llama_cli = llama_cli.resolve()
    llm_path = llm_path.resolve()

    # llama-cli on Windows may use the active console code page for argv. Removing
    # accents keeps Portuguese semantics intact without replacing letters by '?'.
    ascii_prompt = unicodedata.normalize("NFKD", prompt).encode("ascii", "ignore").decode("ascii")
    response_prefix = "NEVE_TRANSLATION_7F3A:"
    instruction = (
        "Translate literally into English for image generation. Preserve every requested detail, "
        "action, and intensity. Never censor, soften, euphemize, or omit nudity, sexual content, "
        "injuries, blood, violence, dismemberment, or gore. Do not expand, embellish, reinterpret, "
        "or add anatomy, composition, consequences, objects, actions, or visual details. In Portuguese, "
        "'arrancar' applied to a body part means rip or tear that body part off, never merely pull it. "
        f"Output exactly one line beginning with {response_prefix}, followed only by the concise translation. "
        f"User request: {ascii_prompt}"
    )
    command = [
        str(llama_cli),
        "-m",
        str(llm_path),
        "-p",
        instruction,
        "-n",
        "256",
        "--temp",
        "0",
        "--top-k",
        "1",
        "--no-display-prompt",
        "--no-show-timings",
        "--no-warmup",
        "--simple-io",
        "--reasoning-format",
        "none",
        "-st",
    ]
    try:
        completed = subprocess.run(
            command,
            cwd=str(llama_cli.parent),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=45,
            check=False,
        )
    except Exception as exc:
        log.warning("Traducao local do prompt de imagem falhou: %s", exc)
        return prompt

    response_matches = re.findall(
        rf"(?m)^\s*{re.escape(response_prefix)}\s*(.+?)\s*$", completed.stdout
    )
    if completed.returncode != 0 or not response_matches:
        log.warning(
            "Traducao local do prompt de imagem nao retornou uma resposta valida (codigo %s)",
            completed.returncode,
        )
        return prompt

    response = response_matches[-1]
    translated = _normalize_image_prompt_text(response)
    if not translated or len(translated) < 4 or translated.lower().startswith(("i cannot", "sorry")):
        return prompt
    return _polish_translated_image_prompt(translated, prompt)


def _ensure_prompt_translator_sync(hf_token: Optional[str] = None) -> Path:
    from huggingface_hub import hf_hub_download

    return Path(
        hf_hub_download(
            repo_id=PROMPT_TRANSLATOR_REPO,
            filename=PROMPT_TRANSLATOR_FILE,
            cache_dir=str(PROMPT_TRANSLATOR_CACHE_DIR),
            token=hf_token or None,
        )
    ).resolve()


_PLURAL_SUBJECT_RE = re.compile(
    r"\b(?:two|three|four|multiple|several|group|crowd|couple|duo|people|characters|"
    r"men|women|girls|boys|dois|duas|tres|quatro|multipl\w*|varios|varias|grupo|"
    r"multidao|casal|dupla|pessoas|personagens|homens|mulheres|meninas|meninos)\b",
    flags=re.IGNORECASE,
)
_SINGULAR_SUBJECT_RE = re.compile(
    r"\b(?:person|character|woman|man|girl|boy|child|baby|cat|dog|animal|creature|"
    r"personagem|pessoa|mulher|homem|menina|menino|crianca|bebe|gato|cachorro|"
    r"animal|criatura)\b",
    flags=re.IGNORECASE,
)
_EXPLICIT_LANDSCAPE_PROMPT_RE = re.compile(
    r"\b(?:landscape|panorama|panoramic|wide shot|wide-angle|widescreen|cityscape|"
    r"battlefield|battle|war|war scene|paisagem|panorama|panoramica|plano aberto|"
    r"grande angular|cidade|guerra|batalha|campo de batalha|cena de guerra)\b",
    flags=re.IGNORECASE,
)
_SCENE_LANDSCAPE_PROMPT_RE = re.compile(
    r"\b(?:street|road|avenue|highway|bridge|railway|airport|harbor|room|interior|"
    r"exterior|building|house|castle|village|forest|mountain|valley|beach|ocean|"
    r"river|lake|field|desert|park|stadium|car|vehicle|truck|bus|motorcycle|"
    r"bicycle|train|airplane|aircraft|boat|ship|spaceship|driving|flying|sailing|"
    r"rua|estrada|avenida|rodovia|ponte|ferrovia|aeroporto|porto|sala|interior|"
    r"exterior|pr[eé]dio|casa|castelo|vila|floresta|montanha|vale|praia|oceano|"
    r"rio|lago|campo|deserto|parque|est[aá]dio|carro|ve[ií]culo|caminh[aã]o|"
    r"[oô]nibus|moto|bicicleta|trem|avi[aã]o|aeronave|barco|navio|nave|"
    r"dirigindo|voando|navegando)\b",
    flags=re.IGNORECASE,
)
_PORTRAIT_PROMPT_RE = re.compile(
    r"\b(?:portrait|headshot|close-up|upper body|full body|vertical|retrato|rosto|"
    r"primeiro plano|meio corpo|corpo inteiro|vertical)\b",
    flags=re.IGNORECASE,
)


def _protect_single_subject_composition(prompt: str, source_prompt: str) -> str:
    combined = f"{source_prompt} {prompt}"
    if _PLURAL_SUBJECT_RE.search(combined) or not _SINGULAR_SUBJECT_RE.search(combined):
        return prompt
    if re.search(r"\b(?:one single|single subject|solo)\b", prompt, flags=re.IGNORECASE):
        return prompt
    return f"one single subject, solo composition, no duplicates, {prompt}"


async def _prepare_image_prompt(prompt: str, hf_token: Optional[str] = None) -> str:
    source_prompt = _normalize_image_prompt_text(prompt)
    prompt = source_prompt
    if not prompt:
        return prompt

    if _looks_english(prompt):
        log.info(
            "Prompt de imagem ja esta em ingles; usando sem traducao: %s",
            _short_log_prompt(prompt),
        )
        return _protect_single_subject_composition(prompt, source_prompt)

    loop = asyncio.get_running_loop()
    try:
        translator_path = await loop.run_in_executor(
            None, _ensure_prompt_translator_sync, hf_token
        )
        translated = await asyncio.wait_for(
            loop.run_in_executor(
                None, _translate_image_prompt_locally_sync, prompt, translator_path
            ),
            timeout=IMAGE_PROMPT_TRANSLATION_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        log.warning(
            "Traducao do prompt de imagem excedeu %.0fs; usando o prompt original",
            IMAGE_PROMPT_TRANSLATION_TIMEOUT_SECONDS,
        )
        translated = prompt
    except Exception as e:
        log.warning("Traducao do prompt de imagem falhou; usando o original: %s", e)
        translated = prompt

    translated = _normalize_image_prompt_text(translated)
    if not translated:
        log.warning("Traducao do prompt de imagem retornou vazia; usando o original")
        translated = prompt

    if translated != prompt:
        log.info(
            "Prompt de imagem traduzido localmente para ingles: %s",
            _short_log_prompt(translated),
        )
    elif _looks_english(prompt):
        log.info("Prompt de imagem confirmado em ingles antes da geracao")
    else:
        log.warning(
            "Prompt de imagem mantido no idioma original porque a traducao nao estava disponivel"
        )
    return _protect_single_subject_composition(translated, source_prompt)


@dataclass(frozen=True)
class _ZImageResources:
    sd_cli: Path
    diffusion_model: Path
    llm: Path
    vae: Path
    llm_vision: Optional[Path] = None


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(4 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _ensure_style_lora(style: str, hf_token: Optional[str] = None) -> Optional[Path]:
    style = normalize_image_style(style)
    spec = ZIMAGE_STYLE_SPECS.get(style)
    if spec is None:
        return None

    destination = LORA_CACHE_DIR / spec.filename
    if destination.is_file() and _file_sha256(destination) == spec.sha256:
        return destination

    temporary = destination.with_suffix(f"{destination.suffix}.download")
    failures: list[str] = []
    civitai_token = str(
        os.environ.get("NEVEAI_CIVITAI_TOKEN")
        or os.environ.get("CIVITAI_API_TOKEN")
        or ""
    ).strip()
    try:
        for source_url in spec.download_urls:
            temporary.unlink(missing_ok=True)
            try:
                headers: dict[str, str] = {}
                source_host = urllib.parse.urlsplit(source_url).netloc.casefold()
                if source_host == "huggingface.co" and hf_token:
                    headers["Authorization"] = f"Bearer {hf_token}"
                elif "civitai.com" in source_host:
                    if civitai_token:
                        separator = "&" if "?" in source_url else "?"
                        source_url = (
                            f"{source_url}{separator}token="
                            f"{urllib.parse.quote(civitai_token, safe='')}"
                        )
                    else:
                        headers["Accept"] = "application/octet-stream"

                _download_file(source_url, temporary, headers=headers)
                if _file_sha256(temporary) != spec.sha256:
                    raise RuntimeError("hash SHA-256 inesperado")
                os.replace(temporary, destination)
                return destination
            except Exception as exc:
                failures.append(f"{urllib.parse.urlsplit(source_url).netloc}: {exc}")

        raise RuntimeError(
            f"Nao foi possivel baixar o estilo {style} com integridade verificada. "
            + " | ".join(failures)
        )
    finally:
        temporary.unlink(missing_ok=True)


def _download_file(
    url: str, destination: Path, headers: Optional[dict[str, str]] = None
):
    destination.parent.mkdir(parents=True, exist_ok=True)
    request_headers = {"User-Agent": "NeveAI/1.0"}
    request_headers.update(headers or {})
    request = urllib.request.Request(url, headers=request_headers)
    with urllib.request.urlopen(request, timeout=600) as response, open(destination, "wb") as output:
        while True:
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            output.write(chunk)


def _download_and_extract_sd_cpp_asset(asset: dict, destination_dir: Path = SD_CPP_DIR):
    url = asset.get("browser_download_url")
    name = asset.get("name")
    if not url or not name:
        raise RuntimeError("Asset invalido no release do stable-diffusion.cpp")

    archive_path = destination_dir / name
    log.info("Baixando stable-diffusion.cpp: %s", name)
    _download_file(url, archive_path)
    try:
        with zipfile.ZipFile(archive_path) as archive:
            archive.extractall(destination_dir)
    finally:
        try:
            archive_path.unlink(missing_ok=True)
        except TypeError:
            if archive_path.exists():
                archive_path.unlink()


def _preferred_sd_cpp_windows_backend() -> str:
    if shutil.which("nvidia-smi"):
        return "cuda12"
    try:
        command = [
            "powershell.exe",
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            "Get-CimInstance Win32_VideoController | ForEach-Object Name",
        ]
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
            **({"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}),
        )
        gpu_names = result.stdout.lower()
        if any(name in gpu_names for name in ("amd", "radeon")):
            return "vulkan"
    except Exception as exc:
        log.debug("Nao foi possivel detectar a GPU para o sd-cli: %s", exc)
    return "cpu"


def _detected_gpu_vram_mib() -> Optional[int]:
    """Return conservative dedicated VRAM detection for memory-policy selection."""
    if shutil.which("nvidia-smi"):
        try:
            result = subprocess.run(
                [
                    "nvidia-smi",
                    "--query-gpu=memory.total",
                    "--format=csv,noheader,nounits",
                ],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
                **({"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}),
            )
            values = [int(line.strip()) for line in result.stdout.splitlines() if line.strip()]
            return max(values) if result.returncode == 0 and values else None
        except (OSError, ValueError, subprocess.SubprocessError):
            return None

    if os.name == "nt" and _preferred_sd_cpp_windows_backend() == "vulkan":
        try:
            result = subprocess.run(
                [
                    "powershell.exe",
                    "-NoProfile",
                    "-NonInteractive",
                    "-Command",
                    "Get-CimInstance Win32_VideoController | "
                    "Where-Object { $_.Name -match 'AMD|Radeon' } | "
                    "ForEach-Object { [uint64]$_.AdapterRAM }",
                ],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            values = [int(line.strip()) // (1024 * 1024) for line in result.stdout.splitlines() if line.strip()]
            return max(values) if result.returncode == 0 and values else None
        except (OSError, ValueError, subprocess.SubprocessError):
            return None

    return None


def _qwen_image_memory_args() -> list[str]:
    vram_mib = _detected_gpu_vram_mib()
    if vram_mib is not None and vram_mib >= QWEN_IMAGE_21_FULL_GPU_MIN_VRAM_MIB:
        log.info("Qwen Image 2.1: auto-fit em GPU (%s MiB de VRAM detectados)", vram_mib)
        return ["--auto-fit", "on", "--vae-tiling"]

    detected = f"{vram_mib} MiB" if vram_mib is not None else "desconhecida"
    log.info("Qwen Image 2.1: offload conservador (VRAM %s)", detected)
    return ["--offload-to-cpu", "--vae-tiling"]


def _supports_native_sage_attention() -> bool:
    if os.name != "nt" or _preferred_sd_cpp_windows_backend() != "cuda12":
        return False
    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=compute_cap",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        first_capability = result.stdout.splitlines()[0].strip()
        return result.returncode == 0 and float(first_capability) >= 8.0
    except (IndexError, OSError, ValueError, subprocess.SubprocessError):
        return False


def _sd_cpp_build_number(version_lines: list[str]) -> int:
    if not version_lines:
        return 0
    match = re.search(r"master-(\d+)", version_lines[0], flags=re.IGNORECASE)
    return int(match.group(1)) if match else 0


def _ensure_sd_cli_binary(require_qwen_image_21: bool = False) -> Path:
    if os.name != "nt":
        if SD_CLI_PATH.exists():
            return SD_CLI_PATH
        raise RuntimeError(
            "sd-cli nao foi encontrado. Instale stable-diffusion.cpp e coloque o binario em "
            f"{SD_CLI_PATH}."
        )

    backend = _preferred_sd_cpp_windows_backend()
    version_file = SD_CPP_DIR / "version.txt"
    installed_backend = ""
    installed_version_lines: list[str] = []
    if version_file.is_file():
        try:
            installed_version_lines = version_file.read_text(encoding="utf-8-sig").splitlines()
            installed_backend = next(
                (line.strip().lower() for line in reversed(installed_version_lines) if line.strip()),
                "",
            )
        except Exception:
            installed_backend = ""

    supports_qwen_image_21 = (
        not require_qwen_image_21
        or _sd_cpp_build_number(installed_version_lines) >= SD_CPP_QWEN_IMAGE_21_MIN_BUILD
    )
    if SD_CLI_PATH.exists() and supports_qwen_image_21 and (
        installed_backend == backend
        or (backend == "cuda12" and not installed_backend)
    ):
        return SD_CLI_PATH

    staging_dir = SD_CPP_DIR.with_name(f"{SD_CPP_DIR.name}.update")
    backup_dir = SD_CPP_DIR.with_name(f"{SD_CPP_DIR.name}.backup")
    if staging_dir.exists():
        shutil.rmtree(staging_dir)
    staging_dir.mkdir(parents=True, exist_ok=True)
    log.info("Preparando stable-diffusion.cpp %s para Windows...", backend)
    request = urllib.request.Request(SD_CPP_RELEASE_API, headers={"User-Agent": "NeveAI/1.0"})
    with urllib.request.urlopen(request, timeout=60) as response:
        release = json.loads(response.read().decode("utf-8"))

    assets = release.get("assets") or []
    asset_pattern = {
        "cuda12": SD_CPP_WIN_CUDA_ASSET,
        "vulkan": SD_CPP_WIN_VULKAN_ASSET,
        "cpu": SD_CPP_WIN_CPU_ASSET,
    }[backend]
    sd_asset = next(
        (asset for asset in assets if fnmatch.fnmatch(asset.get("name", ""), asset_pattern)),
        None,
    )
    cudart_asset = next(
        (asset for asset in assets if asset.get("name") == SD_CPP_WIN_CUDART_ASSET),
        None,
    )
    if not sd_asset or (backend == "cuda12" and not cudart_asset):
        raise RuntimeError(f"Release do stable-diffusion.cpp nao contem o binario Windows {backend} esperado")

    try:
        _download_and_extract_sd_cpp_asset(sd_asset, staging_dir)
        if backend == "cuda12" and cudart_asset is not None:
            _download_and_extract_sd_cpp_asset(cudart_asset, staging_dir)
        staged_cli = staging_dir / SD_CLI_PATH.name
        if not staged_cli.exists():
            raise RuntimeError(f"sd-cli nao foi extraido corretamente em {staged_cli}")
        (staging_dir / "version.txt").write_text(
            f"{str(release.get('tag_name') or 'latest')}\n{backend}\n", encoding="utf-8"
        )

        if backup_dir.exists():
            shutil.rmtree(backup_dir)
        if SD_CPP_DIR.exists():
            os.replace(SD_CPP_DIR, backup_dir)
        try:
            os.replace(staging_dir, SD_CPP_DIR)
        except BaseException:
            if backup_dir.exists() and not SD_CPP_DIR.exists():
                os.replace(backup_dir, SD_CPP_DIR)
            raise
        if backup_dir.exists():
            try:
                shutil.rmtree(backup_dir)
            except Exception as exc:
                log.warning("Runtime antigo sera limpo depois: %s", exc)
    finally:
        if staging_dir.exists():
            shutil.rmtree(staging_dir, ignore_errors=True)
    return SD_CLI_PATH


class _ZImageTurboPipeline:
    """Gerencia os runtimes locais de imagem e executa sd-cli em serie."""

    def __init__(self):
        self._resources: Optional[_ZImageResources] = None
        self._model_id: Optional[str] = None
        self._quality = "neve_image"
        self._edit_mode = False
        self._load_lock = asyncio.Lock()
        self._generation_lock = asyncio.Lock()
        self._request_lock = asyncio.Lock()

    @property
    def is_loaded(self) -> bool:
        return self._resources is not None

    async def load(self, model_id: str, device: str = "cuda", hf_token: Optional[str] = None, quality: str = "neve_image", edit: bool = False):
        async with self._load_lock:
            model_id = normalize_sd_model_id(model_id)
            quality = normalize_image_quality(quality)
            edit = quality in {"neve_image_2", "qwen_image_2_1"} and edit
            if self._resources is not None and self._model_id == model_id and self._quality == quality and self._edit_mode == edit:
                return

            loop = asyncio.get_event_loop()

            def _prepare_sync() -> _ZImageResources:
                from huggingface_hub import hf_hub_download

                sd_cli = _ensure_sd_cli_binary(
                    require_qwen_image_21=quality == "qwen_image_2_1"
                )
                token = hf_token or None

                if quality == "qwen_image_2_1":
                    def download_qwen(repo: str, filename: str, cache_dir: Path) -> Path:
                        return Path(
                            hf_hub_download(
                                repo_id=repo,
                                filename=filename,
                                cache_dir=str(cache_dir),
                                token=token,
                            )
                        )

                    log.info("Baixando/carregando Qwen Image 2.1 Q6_K...")
                    return _ZImageResources(
                        sd_cli=sd_cli,
                        diffusion_model=download_qwen(
                            QWEN_IMAGE_21_REPO, QWEN_IMAGE_21_FILE, GGUF_CACHE_DIR
                        ),
                        llm=download_qwen(
                            QWEN_IMAGE_21_LLM_REPO,
                            QWEN_IMAGE_21_LLM_FILE,
                            QWEN3_CACHE_DIR,
                        ),
                        vae=download_qwen(
                            QWEN_IMAGE_21_VAE_REPO,
                            QWEN_IMAGE_21_VAE_FILE,
                            VAE_CACHE_DIR,
                        ),
                        llm_vision=(
                            download_qwen(
                                QWEN_IMAGE_21_LLM_REPO,
                                QWEN_IMAGE_21_VISION_FILE,
                                QWEN3_CACHE_DIR,
                            )
                            if edit
                            else None
                        ),
                    )

                if edit:
                    def download(repo: str, filename: str) -> Path:
                        return Path(hf_hub_download(repo_id=repo, filename=filename, cache_dir=str(MAGEFLOW_CACHE_DIR), token=token))

                    return _ZImageResources(
                        sd_cli=sd_cli,
                        diffusion_model=download(MAGEFLOW_REPO, MAGEFLOW_EDIT_FILE),
                        llm=download(MAGEFLOW_LLM_REPO, MAGEFLOW_LLM_FILE),
                        vae=download(MAGEFLOW_REPO, MAGEFLOW_VAE_FILE),
                        llm_vision=download(MAGEFLOW_LLM_REPO, MAGEFLOW_VISION_FILE),
                    )

                gguf_repo = ZIMAGE_QUALITY_REPO if quality == "neve_image_2" else model_id
                gguf_file = ZIMAGE_QUALITY_GGUF_FILE if quality == "neve_image_2" else ZIMAGE_GGUF_FILE
                log.info("Baixando/carregando Z-Image-Turbo %s GGUF...", gguf_file)
                diffusion_model = Path(
                    hf_hub_download(
                        repo_id=gguf_repo,
                        filename=gguf_file,
                        cache_dir=str(GGUF_CACHE_DIR),
                        token=token,
                    )
                )

                llm_repo = (
                    ZIMAGE_UNCENSORED_LLM_REPO
                    if quality == "neve_image_2"
                    else QWEN3_LLM_REPO
                )
                llm_file = (
                    ZIMAGE_UNCENSORED_LLM_FILE
                    if quality == "neve_image_2"
                    else QWEN3_LLM_FILE
                )
                log.info(
                    "Baixando/carregando text encoder Z-Image %s Q4_K_M...",
                    "abliterated" if quality == "neve_image_2" else "padrao",
                )
                llm = Path(
                    hf_hub_download(
                        repo_id=llm_repo,
                        filename=llm_file,
                        cache_dir=str(QWEN3_CACHE_DIR),
                        token=token,
                    )
                )

                log.info("Baixando/carregando VAE do Z-Image-Turbo...")
                vae = Path(
                    hf_hub_download(
                        repo_id=ZIMAGE_VAE_REPO,
                        filename=ZIMAGE_VAE_FILE,
                        cache_dir=str(VAE_CACHE_DIR),
                        token=token,
                    )
                )

                return _ZImageResources(sd_cli=sd_cli, diffusion_model=diffusion_model, llm=llm, vae=vae)

            self._resources = await loop.run_in_executor(None, _prepare_sync)
            self._model_id = model_id
            self._quality = quality
            self._edit_mode = edit
            runtime_name = (
                "Qwen Image 2.1"
                if quality == "qwen_image_2_1"
                else "Mage-Flow-Edit" if edit else "Z-Image-Turbo"
            )
            log.info("%s pronto via stable-diffusion.cpp", runtime_name)

    async def unload(self):
        async with self._request_lock:
            async with self._load_lock:
                self._resources = None
                self._model_id = None
                self._quality = "neve_image"
                self._edit_mode = False

    async def run(
        self,
        model_id: str,
        hf_token: Optional[str],
        quality: str,
        style: str = "none",
        progress_callback: Optional[ImageProgressCallback] = None,
        dimensions_callback: Optional[ImageDimensionsCallback] = None,
        **kwargs,
    ) -> str:
        async with self._request_lock:
            quality = normalize_image_quality(quality)
            style = normalize_image_style(style) if quality == "neve_image_2" else "none"
            has_reference = bool(
                kwargs.get("init_image_references") or kwargs.get("init_image_reference")
            )
            use_mageflow = quality == "neve_image_2" and has_reference and style == "none"
            needs_vision = quality == "qwen_image_2_1" and has_reference
            load_task = asyncio.create_task(
                self.load(
                    model_id,
                    hf_token=hf_token,
                    quality=quality,
                    edit=use_mageflow or needs_vision,
                )
            )
            try:
                loading_progress = 1
                if progress_callback is not None:
                    await progress_callback(loading_progress)
                while not load_task.done():
                    done, _ = await asyncio.wait({load_task}, timeout=1.0)
                    if done:
                        break
                    loading_progress = min(20, loading_progress + 1)
                    if progress_callback is not None:
                        await progress_callback(loading_progress)
                await load_task
            except BaseException:
                if not load_task.done():
                    load_task.cancel()
                    await asyncio.gather(load_task, return_exceptions=True)
                raise
            if progress_callback is not None:
                await progress_callback(max(21, loading_progress))
            return await self.generate(
                hf_token=hf_token,
                style=style,
                progress_callback=progress_callback,
                dimensions_callback=dimensions_callback,
                **kwargs,
            )

    async def generate(
        self,
        prompt: str,
        width: int = MAX_IMAGE_WIDTH,
        height: int = MAX_IMAGE_HEIGHT,
        steps: int = MAX_IMAGE_STEPS,
        guidance_scale: float = DEFAULT_CFG_SCALE,
        init_image_reference: Optional[str] = None,
        init_image_references: Optional[list[str]] = None,
        resolution: str = "1:1",
        user_id: Optional[str] = None,
        hf_token: Optional[str] = None,
        style: str = "none",
        progress_callback: Optional[ImageProgressCallback] = None,
        dimensions_callback: Optional[ImageDimensionsCallback] = None,
    ) -> str:
        if not self.is_loaded or self._resources is None:
            raise RuntimeError("Runtime local de imagem nao carregado")

        if progress_callback is not None:
            await progress_callback(22)
        qwen_image_mode = self._quality == "qwen_image_2_1"
        prompt = (
            _normalize_image_prompt_text(prompt)
            if qwen_image_mode
            else await _prepare_image_prompt(prompt, hf_token)
        )
        if not prompt:
            raise RuntimeError("Prompt vazio para geracao de imagem")
        if progress_callback is not None:
            await progress_callback(26)

        style = normalize_image_style(style) if self._quality == "neve_image_2" else "none"
        style_spec = ZIMAGE_STYLE_SPECS.get(style)
        style_lora = None
        if style_spec is not None:
            if progress_callback is not None:
                await progress_callback(27)
            style_lora = await asyncio.get_event_loop().run_in_executor(
                None, _ensure_style_lora, style, hf_token
            )
            if style_spec.prompt_prefix:
                prompt = f"{style_spec.prompt_prefix}, {prompt}"
            prompt = f"{prompt} <lora:{style_lora.stem}:{style_spec.weight:g}>"
        if progress_callback is not None:
            await progress_callback(30)

        reference_values = list(init_image_references or [])
        if init_image_reference and init_image_reference not in reference_values:
            reference_values.insert(0, init_image_reference)
        reference_images = (
            await _prepare_reference_images(reference_values, user_id=user_id)
            if qwen_image_mode
            else []
        )
        init_image = (
            None
            if qwen_image_mode
            else await _prepare_init_image(
                reference_values[0] if reference_values else None,
                user_id=user_id,
            )
        )

        quality_mode = self._quality == "neve_image_2"
        if qwen_image_mode:
            width, height = qwen_image_dimensions(resolution)
        elif quality_mode:
            width, height = quality_image_dimensions(resolution)
        else:
            width = _align_image_dim(width, MAX_IMAGE_WIDTH, MAX_IMAGE_WIDTH)
            height = _align_image_dim(height, MAX_IMAGE_HEIGHT, MAX_IMAGE_HEIGHT)
            if init_image is not None:
                width, height = _fit_init_image_dimensions(
                    init_image, width, height, MAX_IMAGE_WIDTH
                )
        if dimensions_callback is not None:
            await dimensions_callback(width, height)
        if progress_callback is not None:
            await progress_callback(33)
        if qwen_image_mode:
            steps = QWEN_IMAGE_21_STEPS
            cfg = QWEN_IMAGE_21_CFG_SCALE
        else:
            steps = 4 if self._edit_mode else _clamp_int(steps, QUALITY_IMAGE_STEPS if quality_mode else MAX_IMAGE_STEPS, 1, QUALITY_IMAGE_STEPS if quality_mode else MAX_IMAGE_STEPS)
            cfg = _cfg_scale(guidance_scale)
        seed = random.randint(0, 2**31 - 1)
        filename = f"sd_{int(time.time())}_{seed}.png"
        output_path = IMAGE_OUTPUT_DIR / filename
        log.info(
            "Prompt final enviado ao sd-cli (seed=%s): %s",
            seed,
            _short_log_prompt(prompt),
        )

        attention_args = (
            ["--sage-attn"]
            if qwen_image_mode and _supports_native_sage_attention()
            else ["--diffusion-fa"]
        )
        cmd = [
            str(self._resources.sd_cli),
            "--diffusion-model",
            str(self._resources.diffusion_model),
            "--llm",
            str(self._resources.llm),
            "--vae",
            str(self._resources.vae),
            "-p",
            prompt,
            "-W",
            str(width),
            "-H",
            str(height),
            "--steps",
            str(steps),
            "--cfg-scale",
            f"{cfg:g}",
            *attention_args,
            *(
                ["--lora-model-dir", str(LORA_CACHE_DIR)]
                if style_lora is not None
                else []
            ),
            *([] if quality_mode or qwen_image_mode else ["--offload-to-cpu"]),
            *(_qwen_image_memory_args() if qwen_image_mode else []),
            *(["--vae-conv-direct"] if quality_mode and not self._edit_mode and not qwen_image_mode else []),
            *(
                ["--llm_vision", str(self._resources.llm_vision)]
                if self._resources.llm_vision is not None
                else []
            ),
            *(["--sampling-method", "euler"] if self._edit_mode or qwen_image_mode else []),
            "-s",
            str(seed),
            "-o",
            str(output_path),
        ]
        if qwen_image_mode:
            for reference_image in reference_images:
                cmd.extend(["-r", str(reference_image.path)])
            if reference_images:
                cmd.extend(["--ref-image-args", "preset=qwen,vlm_size=768"])
        elif init_image is not None:
            if self._edit_mode:
                cmd.extend(["--ref-image", str(init_image.path)])
            else:
                cmd.extend(["--init-img", str(init_image.path), "--strength", f"{DEFAULT_IMG2IMG_STRENGTH:g}"])

        env = os.environ.copy()
        env["PATH"] = f"{SD_CPP_DIR}{os.pathsep}{env.get('PATH', '')}"

        try:
            async with self._generation_lock:
                has_input = bool(reference_images) if qwen_image_mode else init_image is not None
                mode = "image-edit" if has_input else "txt2img"
                runtime_name = "Qwen Image 2.1" if qwen_image_mode else "Z-Image-Turbo"
                log.info("Gerando imagem %s %s %sx%s, steps=%s, cfg=%s", runtime_name, mode, width, height, steps, cfg)
                process = await asyncio.create_subprocess_exec(
                    *cmd,
                    cwd=str(SD_CPP_DIR),
                    env=env,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )

                stdout_chunks: list[bytes] = []
                stderr_chunks: list[bytes] = []
                last_progress = 33

                async def read_stream(
                    stream: Optional[asyncio.StreamReader], chunks: list[bytes]
                ) -> None:
                    nonlocal last_progress
                    if stream is None:
                        return
                    carry = ""
                    while True:
                        chunk = await stream.read(2048)
                        if not chunk:
                            break
                        chunks.append(chunk)
                        carry = (carry + chunk.decode("utf-8", errors="replace"))[-1024:]
                        for match in re.finditer(r"(?<!\d)(\d+)\s*/\s*(\d+)(?!\d)", carry):
                            current = int(match.group(1))
                            total = int(match.group(2))
                            if total != steps or current < 0 or current > total:
                                continue
                            percent = min(
                                91,
                                max(34, 34 + round((current / total) * 57)),
                            )
                            if percent <= last_progress:
                                continue
                            last_progress = percent
                            if progress_callback is not None:
                                try:
                                    await progress_callback(percent)
                                except Exception as exc:
                                    log.debug("Image progress callback failed: %s", exc)

                async def communicate_with_progress() -> None:
                    async def pulse_progress() -> None:
                        nonlocal last_progress
                        while process.returncode is None:
                            await asyncio.sleep(1.0)
                            if process.returncode is not None:
                                break
                            if last_progress < 98:
                                last_progress += 1
                                if progress_callback is not None:
                                    try:
                                        await progress_callback(last_progress)
                                    except Exception as exc:
                                        log.debug("Image progress pulse failed: %s", exc)

                    await asyncio.gather(
                        read_stream(process.stdout, stdout_chunks),
                        read_stream(process.stderr, stderr_chunks),
                        process.wait(),
                        pulse_progress(),
                    )

                try:
                    await asyncio.wait_for(
                        communicate_with_progress(), timeout=SD_CLI_TIMEOUT_SECONDS
                    )
                except asyncio.CancelledError:
                    if process.returncode is None:
                        process.kill()
                        await process.wait()
                    raise
                except asyncio.TimeoutError:
                    process.kill()
                    await process.wait()
                    raise RuntimeError("Geracao de imagem excedeu o tempo limite do stable-diffusion.cpp")
        finally:
            temporary_images = [*reference_images]
            if init_image is not None:
                temporary_images.append(init_image)
            for temporary_image in temporary_images:
                try:
                    temporary_image.path.unlink(missing_ok=True)
                except TypeError:
                    if temporary_image.path.exists():
                        temporary_image.path.unlink()
                except Exception as e:
                    log.debug("Nao foi possivel remover imagem temporaria de referencia: %s", e)

        output = b"".join(stdout_chunks) + b"\n" + b"".join(stderr_chunks)
        output_text = output.decode("utf-8", errors="replace")
        if process.returncode != 0:
            raise RuntimeError(f"stable-diffusion.cpp falhou (codigo {process.returncode}): {output_text[-4000:]}")

        if not output_path.exists() or output_path.stat().st_size <= 0:
            raise RuntimeError(f"stable-diffusion.cpp terminou sem gerar a imagem: {output_text[-4000:]}")

        if progress_callback is not None:
            await progress_callback(99)
        raw = output_path.read_bytes()
        b64 = base64.b64encode(raw).decode("utf-8")
        return f"data:image/png;base64,{b64}"


_sd_pipeline = _ZImageTurboPipeline()


class GenerateForm(BaseModel):
    prompt: str
    width: Optional[int] = None
    height: Optional[int] = None
    steps: Optional[int] = None
    guidance_scale: Optional[float] = None
    init_image: Optional[str] = None
    init_images: Optional[list[str]] = None
    quality: str = "neve_image"
    style: str = "none"
    resolution: str = "1:1"


class ConfigForm(BaseModel):
    ENABLE_STABLE_DIFFUSION: Optional[bool] = None
    STABLE_DIFFUSION_MODEL: Optional[str] = None
    STABLE_DIFFUSION_HF_TOKEN: Optional[str] = None
    STABLE_DIFFUSION_WIDTH: Optional[int] = None
    STABLE_DIFFUSION_HEIGHT: Optional[int] = None
    STABLE_DIFFUSION_STEPS: Optional[int] = None
    STABLE_DIFFUSION_GUIDANCE_SCALE: Optional[float] = None


@router.get("/config")
async def get_sd_config(request: Request, user=Depends(get_admin_user)):
    return {
        "ENABLE_STABLE_DIFFUSION": request.app.state.config.ENABLE_STABLE_DIFFUSION,
        "STABLE_DIFFUSION_MODEL": normalize_sd_model_id(request.app.state.config.STABLE_DIFFUSION_MODEL),
        "STABLE_DIFFUSION_HF_TOKEN": request.app.state.config.STABLE_DIFFUSION_HF_TOKEN,
        "STABLE_DIFFUSION_WIDTH": _align_image_dim(
            request.app.state.config.STABLE_DIFFUSION_WIDTH, MAX_IMAGE_WIDTH, MAX_IMAGE_WIDTH
        ),
        "STABLE_DIFFUSION_HEIGHT": _align_image_dim(
            request.app.state.config.STABLE_DIFFUSION_HEIGHT, MAX_IMAGE_HEIGHT, MAX_IMAGE_HEIGHT
        ),
        "STABLE_DIFFUSION_STEPS": _clamp_int(
            request.app.state.config.STABLE_DIFFUSION_STEPS, MAX_IMAGE_STEPS, 1, MAX_IMAGE_STEPS
        ),
        "STABLE_DIFFUSION_GUIDANCE_SCALE": _cfg_scale(request.app.state.config.STABLE_DIFFUSION_GUIDANCE_SCALE),
        "is_loaded": _sd_pipeline.is_loaded,
    }


@router.post("/config/update")
async def update_sd_config(request: Request, form_data: ConfigForm, user=Depends(get_admin_user)):
    if form_data.ENABLE_STABLE_DIFFUSION is not None:
        request.app.state.config.ENABLE_STABLE_DIFFUSION = form_data.ENABLE_STABLE_DIFFUSION
    if form_data.STABLE_DIFFUSION_MODEL is not None:
        request.app.state.config.STABLE_DIFFUSION_MODEL = normalize_sd_model_id(form_data.STABLE_DIFFUSION_MODEL)
    if form_data.STABLE_DIFFUSION_HF_TOKEN is not None:
        request.app.state.config.STABLE_DIFFUSION_HF_TOKEN = form_data.STABLE_DIFFUSION_HF_TOKEN
    if form_data.STABLE_DIFFUSION_WIDTH is not None:
        request.app.state.config.STABLE_DIFFUSION_WIDTH = _align_image_dim(
            form_data.STABLE_DIFFUSION_WIDTH, MAX_IMAGE_WIDTH, MAX_IMAGE_WIDTH
        )
    if form_data.STABLE_DIFFUSION_HEIGHT is not None:
        request.app.state.config.STABLE_DIFFUSION_HEIGHT = _align_image_dim(
            form_data.STABLE_DIFFUSION_HEIGHT, MAX_IMAGE_HEIGHT, MAX_IMAGE_HEIGHT
        )
    if form_data.STABLE_DIFFUSION_STEPS is not None:
        request.app.state.config.STABLE_DIFFUSION_STEPS = _clamp_int(
            form_data.STABLE_DIFFUSION_STEPS, MAX_IMAGE_STEPS, 1, MAX_IMAGE_STEPS
        )
    if form_data.STABLE_DIFFUSION_GUIDANCE_SCALE is not None:
        request.app.state.config.STABLE_DIFFUSION_GUIDANCE_SCALE = _cfg_scale(form_data.STABLE_DIFFUSION_GUIDANCE_SCALE)
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

    model_id = normalize_sd_model_id(request.app.state.config.STABLE_DIFFUSION_MODEL)
    quality = normalize_image_quality(form_data.quality)
    quality_mode = quality == "neve_image_2"
    qwen_image_mode = quality == "qwen_image_2_1"
    max_width = QUALITY_IMAGE_WIDTH if quality_mode else MAX_IMAGE_WIDTH
    max_height = QUALITY_IMAGE_HEIGHT if quality_mode else MAX_IMAGE_HEIGHT
    max_steps = QUALITY_IMAGE_STEPS if quality_mode else MAX_IMAGE_STEPS
    if qwen_image_mode or quality == "qwen_image_2s":
        width, height = qwen_image_dimensions(form_data.resolution)
        steps = 6 if quality == "qwen_image_2s" else QWEN_IMAGE_21_STEPS
    else:
        width = _align_image_dim(form_data.width or (max_width if quality_mode else request.app.state.config.STABLE_DIFFUSION_WIDTH), max_width, max_width)
        height = _align_image_dim(form_data.height or (max_height if quality_mode else request.app.state.config.STABLE_DIFFUSION_HEIGHT), max_height, max_height)
        steps = _clamp_int(form_data.steps or (max_steps if quality_mode else request.app.state.config.STABLE_DIFFUSION_STEPS), max_steps, 1, max_steps)
    guidance_scale = _cfg_scale(
        form_data.guidance_scale
        if form_data.guidance_scale is not None
        else request.app.state.config.STABLE_DIFFUSION_GUIDANCE_SCALE
    )

    from neveai.routers.llamacpp import model_manager

    llm_standby_info = None
    try:
        llm_standby_info = await model_manager.standby()
    except Exception as e:
        log.warning("Failed to put LLM in standby: %s", e)

    try:
        hf_token = str(request.app.state.config.STABLE_DIFFUSION_HF_TOKEN) or None
        if quality == "qwen_image_2s":
            from neveai.routers.image_fast_generation import neve_image_2s_runtime

            references = list(form_data.init_images or [])
            if form_data.init_image and form_data.init_image not in references:
                references.insert(0, form_data.init_image)
            data_uri = await neve_image_2s_runtime.run(
                prompt=form_data.prompt,
                resolution=form_data.resolution,
                references=references,
                user_id=getattr(user, "id", None),
                progress=lambda _: asyncio.sleep(0),
            )
        else:
            data_uri = await _sd_pipeline.run(
                model_id=model_id,
                hf_token=hf_token,
                quality=quality,
                style=form_data.style,
                resolution=form_data.resolution,
                prompt=form_data.prompt,
                width=width,
                height=height,
                steps=steps,
                guidance_scale=guidance_scale,
                init_image_reference=form_data.init_image,
                init_image_references=form_data.init_images,
                user_id=getattr(user, "id", None),
            )
        return {"url": data_uri}
    finally:
        if llm_standby_info is not None:
            try:
                from neveai.routers.llamacpp import model_manager as mm

                await mm.resume(llm_standby_info)
            except Exception as e:
                log.warning("Failed to restore LLM from standby: %s", e)
