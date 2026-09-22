"""
Z-Image-Turbo local -- geracao de imagem via stable-diffusion.cpp.

O runtime usa o diffusion model GGUF do Z-Image-Turbo, Qwen3-4B como text
encoder e o VAE publico distribuido com o Z-Image-Turbo.

Resolucao: 768 x 768
Steps    : 8
Modelo   : leejet/Z-Image-Turbo-GGUF / z_image_turbo-Q4_0.gguf
"""

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
ZIMAGE_QUALITY_GGUF_FILE = "z_image_turbo-Q8_0.gguf"
QWEN3_LLM_REPO = "unsloth/Qwen3-4B-Instruct-2507-GGUF"
QWEN3_LLM_FILE = "Qwen3-4B-Instruct-2507-Q4_K_M.gguf"
PROMPT_TRANSLATOR_REPO = "mradermacher/Huihui-Qwen3-4B-Instruct-2507-abliterated-GGUF"
PROMPT_TRANSLATOR_FILE = "Huihui-Qwen3-4B-Instruct-2507-abliterated.Q4_K_M.gguf"
ZIMAGE_VAE_REPO = "Comfy-Org/z_image_turbo"
ZIMAGE_VAE_FILE = "split_files/vae/ae.safetensors"
MAGEFLOW_REPO = "gguf-org/mageflow-gguf"
MAGEFLOW_EDIT_FILE = "mageflow-edit-turbo-nvfp4.gguf"
MAGEFLOW_VISION_FILE = "mmproj-qwen3vl-4b-it-f16.gguf"
MAGEFLOW_VAE_FILE = "pig_mageflow_vae_fp32-f16.gguf"
MAGEFLOW_LLM_REPO = "Qwen/Qwen3-VL-4B-Instruct-GGUF"
MAGEFLOW_LLM_FILE = "Qwen3VL-4B-Instruct-Q4_K_M.gguf"

MAX_IMAGE_WIDTH = 768
MAX_IMAGE_HEIGHT = 768
MAX_IMAGE_STEPS = 8
QUALITY_IMAGE_WIDTH = 1280
QUALITY_IMAGE_HEIGHT = 720
QUALITY_IMAGE_STEPS = 8
QUALITY_IMAGE_SQUARE = 960
QUALITY_IMAGE_PORTRAIT_WIDTH = 768
QUALITY_IMAGE_PORTRAIT_HEIGHT = 1024
QUALITY_IMAGE_MAX_DIM = 1280
QUALITY_IMAGE_PIXEL_BUDGET = QUALITY_IMAGE_WIDTH * QUALITY_IMAGE_HEIGHT
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
    "realistic": _ZImageStyle(
        download_urls=(
            "https://huggingface.co/Kutches/ImageZ/resolve/main/aestheticphotoz4.safetensors?download=true",
            "https://civitai.com/api/download/models/2512057",
        ),
        filename="neve-realistic.safetensors",
        sha256="3e9b33455a0437d64e61a94baf1cb8e3e9e28f2026b3af4786a96514e9e1bcf2",
        weight=0.7,
        prompt_prefix="aesthetic amateur photo",
    ),
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
    "surreal": _ZImageStyle(
        download_urls=(
            "https://huggingface.co/alexrzem/zit-loras/resolve/main/turbo/Artist_-_Daubrez_Painterly_Style_-_ZImageTurbo_-_blairesilver13.safetensors?download=true",
            "https://civitai.com/api/download/models/2477908",
        ),
        filename="neve-surreal.safetensors",
        sha256="a3827f602c19b8f6310a4cd4d6c3095a9c7b18e416099c47e0827694a7cd3e48",
        weight=1.0,
        prompt_prefix="DBRZ",
    ),
    "conceptual": _ZImageStyle(
        download_urls=("https://civitai.com/api/download/models/2921054",),
        filename="neve-conceptual.safetensors",
        sha256="561f707182a2881da2f656d0ce64399386ce0438fbe8c1c4d350f04a1af17f61",
        weight=0.7,
        prompt_prefix="Bradhamel art style",
    ),
    "comics": _ZImageStyle(
        download_urls=("https://civitai.com/api/download/models/2961085",),
        filename="neve-comics.safetensors",
        sha256="33eef7470d18b25c578c235f27d118252e265e578f38b1e1f888222e89097182",
        weight=0.75,
        prompt_prefix="Bradhamel art style, comic book illustration",
    ),
    "analog": _ZImageStyle(
        download_urls=(
            "https://huggingface.co/atMrMattV/Visione/resolve/main/models/styles/HI8.safetensors?download=true",
            "https://civitai.com/api/download/models/2456725",
        ),
        filename="neve-analog.safetensors",
        sha256="51f37cfe4466ed57ed04e1690dd6b3c409f1dc76c31d3dff7148ff002f5cb00a",
        weight=0.9,
        prompt_prefix="2000s analog amateur photography",
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
    marker = "NEVE_IMAGE_PROMPT_END_7F3A"
    instruction = (
        "Translate the user request into English for an image generator. Preserve exactly "
        "the requested content. Do not invent a setting, clothing, colors, pose, objects, "
        "mood, or story. Return only the final prompt without quotes or explanation. "
        f"User request: {ascii_prompt} {marker}"
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

    if completed.returncode != 0 or marker not in completed.stdout:
        log.warning(
            "Traducao local do prompt de imagem nao retornou uma resposta valida (codigo %s)",
            completed.returncode,
        )
        return prompt

    response = completed.stdout.split(marker, 1)[-1].replace(marker, "")
    response = re.split(r"\n\s*Exiting\.\.\.\s*$", response, maxsplit=1)[0]
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
_LANDSCAPE_PROMPT_RE = re.compile(
    r"\b(?:landscape|panorama|panoramic|wide shot|wide-angle|widescreen|cityscape|"
    r"battlefield|battle|war|war scene|paisagem|panorama|panoramica|plano aberto|"
    r"grande angular|cidade|guerra|batalha|campo de batalha|cena de guerra)\b",
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


def _quality_image_dimensions(prompt: str) -> tuple[int, int]:
    if _LANDSCAPE_PROMPT_RE.search(prompt):
        return QUALITY_IMAGE_WIDTH, QUALITY_IMAGE_HEIGHT
    if _PORTRAIT_PROMPT_RE.search(prompt) or _SINGULAR_SUBJECT_RE.search(prompt):
        return QUALITY_IMAGE_PORTRAIT_WIDTH, QUALITY_IMAGE_PORTRAIT_HEIGHT
    return QUALITY_IMAGE_SQUARE, QUALITY_IMAGE_SQUARE


def _fit_quality_init_image_dimensions(init_image: _InitImage) -> tuple[int, int]:
    if init_image.width <= 0 or init_image.height <= 0:
        return QUALITY_IMAGE_SQUARE, QUALITY_IMAGE_SQUARE

    scale = min(
        QUALITY_IMAGE_MAX_DIM / init_image.width,
        QUALITY_IMAGE_MAX_DIM / init_image.height,
        (QUALITY_IMAGE_PIXEL_BUDGET / (init_image.width * init_image.height)) ** 0.5,
    )
    width = max(256, min(QUALITY_IMAGE_MAX_DIM, int(init_image.width * scale) // 16 * 16))
    height = max(256, min(QUALITY_IMAGE_MAX_DIM, int(init_image.height * scale) // 16 * 16))
    return width, height


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
    try:
        for source_url in spec.download_urls:
            temporary.unlink(missing_ok=True)
            try:
                headers: dict[str, str] = {}
                if "civitai.com/" in source_url:
                    civitai_token = str(
                        os.environ.get("NEVEAI_CIVITAI_TOKEN")
                        or os.environ.get("CIVITAI_API_TOKEN")
                        or ""
                    ).strip()
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


def _download_and_extract_sd_cpp_asset(asset: dict):
    url = asset.get("browser_download_url")
    name = asset.get("name")
    if not url or not name:
        raise RuntimeError("Asset invalido no release do stable-diffusion.cpp")

    archive_path = SD_CPP_DIR / name
    log.info("Baixando stable-diffusion.cpp: %s", name)
    _download_file(url, archive_path)
    try:
        with zipfile.ZipFile(archive_path) as archive:
            archive.extractall(SD_CPP_DIR)
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


def _ensure_sd_cli_binary() -> Path:
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
    if version_file.is_file():
        try:
            installed_backend = next(
                (line.strip().lower() for line in reversed(version_file.read_text(encoding="utf-8-sig").splitlines()) if line.strip()),
                "",
            )
        except Exception:
            installed_backend = ""

    if SD_CLI_PATH.exists() and (
        installed_backend == backend
        or (backend == "cuda12" and not installed_backend)
    ):
        return SD_CLI_PATH

    if SD_CPP_DIR.exists():
        shutil.rmtree(SD_CPP_DIR)
    SD_CPP_DIR.mkdir(parents=True, exist_ok=True)
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

    _download_and_extract_sd_cpp_asset(sd_asset)
    if backend == "cuda12" and cudart_asset is not None:
        _download_and_extract_sd_cpp_asset(cudart_asset)
    if not SD_CLI_PATH.exists():
        raise RuntimeError(f"sd-cli nao foi extraido corretamente em {SD_CLI_PATH}")
    version_file.write_text(
        f"{str(release.get('tag_name') or 'latest')}\n{backend}\n", encoding="utf-8"
    )
    return SD_CLI_PATH


class _ZImageTurboPipeline:
    """Gerencia os recursos Z-Image-Turbo e executa sd-cli de forma serializada."""

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
            quality = "neve_image_2" if quality == "neve_image_2" else "neve_image"
            edit = quality == "neve_image_2" and edit
            if self._resources is not None and self._model_id == model_id and self._quality == quality and self._edit_mode == edit:
                return

            loop = asyncio.get_event_loop()

            def _prepare_sync() -> _ZImageResources:
                from huggingface_hub import hf_hub_download

                sd_cli = _ensure_sd_cli_binary()
                token = hf_token or None

                if edit:
                    def download(repo: str, filename: str) -> Path:
                        return Path(hf_hub_download(repo_id=repo, filename=filename, cache_dir=str(MAGEFLOW_CACHE_DIR), token=token))

                    return _ZImageResources(
                        sd_cli=sd_cli,
                        diffusion_model=download(MAGEFLOW_REPO, MAGEFLOW_EDIT_FILE),
                        llm=download(MAGEFLOW_LLM_REPO, MAGEFLOW_LLM_FILE),
                        vae=download(MAGEFLOW_REPO, MAGEFLOW_VAE_FILE),
                        llm_vision=download(MAGEFLOW_REPO, MAGEFLOW_VISION_FILE),
                    )

                gguf_file = ZIMAGE_QUALITY_GGUF_FILE if quality == "neve_image_2" else ZIMAGE_GGUF_FILE
                log.info("Baixando/carregando Z-Image-Turbo %s GGUF...", gguf_file)
                diffusion_model = Path(
                    hf_hub_download(
                        repo_id=model_id,
                        filename=gguf_file,
                        cache_dir=str(GGUF_CACHE_DIR),
                        token=token,
                    )
                )

                log.info("Baixando/carregando text encoder Qwen3-4B Q4_K_M...")
                llm = Path(
                    hf_hub_download(
                        repo_id=QWEN3_LLM_REPO,
                        filename=QWEN3_LLM_FILE,
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
            log.info("%s pronto via stable-diffusion.cpp", "Mage-Flow-Edit" if edit else "Z-Image-Turbo")

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
            quality = "neve_image_2" if quality == "neve_image_2" else "neve_image"
            style = normalize_image_style(style) if quality == "neve_image_2" else "none"
            use_mageflow = bool(kwargs.get("init_image_reference")) and style == "none"
            await self.load(
                model_id,
                hf_token=hf_token,
                quality=quality,
                edit=use_mageflow,
            )
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
        user_id: Optional[str] = None,
        hf_token: Optional[str] = None,
        style: str = "none",
        progress_callback: Optional[ImageProgressCallback] = None,
        dimensions_callback: Optional[ImageDimensionsCallback] = None,
    ) -> str:
        if not self.is_loaded or self._resources is None:
            raise RuntimeError("Z-Image image runtime nao carregado")

        prompt = await _prepare_image_prompt(prompt, hf_token)
        if not prompt:
            raise RuntimeError("Prompt vazio para geracao de imagem")

        style = normalize_image_style(style)
        style_spec = ZIMAGE_STYLE_SPECS.get(style)
        style_lora = None
        if style_spec is not None:
            style_lora = await asyncio.get_event_loop().run_in_executor(
                None, _ensure_style_lora, style, hf_token
            )
            if style_spec.prompt_prefix:
                prompt = f"{style_spec.prompt_prefix}, {prompt}"
            prompt = f"{prompt} <lora:{style_lora.stem}:{style_spec.weight:g}>"

        init_image = await _prepare_init_image(init_image_reference, user_id=user_id)

        quality_mode = self._quality == "neve_image_2"
        if quality_mode:
            if init_image is not None:
                width, height = _fit_quality_init_image_dimensions(init_image)
            else:
                width, height = _quality_image_dimensions(prompt)
        else:
            width = _align_image_dim(width, MAX_IMAGE_WIDTH, MAX_IMAGE_WIDTH)
            height = _align_image_dim(height, MAX_IMAGE_HEIGHT, MAX_IMAGE_HEIGHT)
            if init_image is not None:
                width, height = _fit_init_image_dimensions(
                    init_image, width, height, MAX_IMAGE_WIDTH
                )
        if dimensions_callback is not None:
            await dimensions_callback(width, height)
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
            "--diffusion-fa",
            *(
                ["--lora-model-dir", str(LORA_CACHE_DIR)]
                if style_lora is not None
                else []
            ),
            *([] if quality_mode else ["--offload-to-cpu"]),
            *(["--vae-conv-direct"] if quality_mode and not self._edit_mode else []),
            *(["--llm_vision", str(self._resources.llm_vision), "--sampling-method", "euler"] if self._edit_mode else []),
            "-s",
            str(seed),
            "-o",
            str(output_path),
        ]
        if init_image is not None:
            if self._edit_mode:
                cmd.extend(["--ref-image", str(init_image.path)])
            else:
                cmd.extend(["--init-img", str(init_image.path), "--strength", f"{DEFAULT_IMG2IMG_STRENGTH:g}"])

        env = os.environ.copy()
        env["PATH"] = f"{SD_CPP_DIR}{os.pathsep}{env.get('PATH', '')}"

        try:
            async with self._generation_lock:
                mode = "img2img" if init_image is not None else "txt2img"
                log.info("Gerando imagem Z-Image-Turbo %s %sx%s, steps=%s, cfg=%s", mode, width, height, steps, cfg)
                process = await asyncio.create_subprocess_exec(
                    *cmd,
                    cwd=str(SD_CPP_DIR),
                    env=env,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )

                stdout_chunks: list[bytes] = []
                stderr_chunks: list[bytes] = []
                last_progress = -1

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
                            percent = min(95, max(1, round((current / total) * 95)))
                            if percent <= last_progress:
                                continue
                            last_progress = percent
                            if progress_callback is not None:
                                try:
                                    await progress_callback(percent)
                                except Exception as exc:
                                    log.debug("Image progress callback failed: %s", exc)

                async def communicate_with_progress() -> None:
                    await asyncio.gather(
                        read_stream(process.stdout, stdout_chunks),
                        read_stream(process.stderr, stderr_chunks),
                        process.wait(),
                    )

                try:
                    await asyncio.wait_for(
                        communicate_with_progress(), timeout=SD_CLI_TIMEOUT_SECONDS
                    )
                except asyncio.TimeoutError:
                    process.kill()
                    await process.wait()
                    raise RuntimeError("Geracao de imagem excedeu o tempo limite do stable-diffusion.cpp")
        finally:
            if init_image is not None:
                try:
                    init_image.path.unlink(missing_ok=True)
                except TypeError:
                    if init_image.path.exists():
                        init_image.path.unlink()
                except Exception as e:
                    log.debug("Nao foi possivel remover imagem temporaria de img2img: %s", e)

        output = b"".join(stdout_chunks) + b"\n" + b"".join(stderr_chunks)
        output_text = output.decode("utf-8", errors="replace")
        if process.returncode != 0:
            raise RuntimeError(f"stable-diffusion.cpp falhou (codigo {process.returncode}): {output_text[-4000:]}")

        if not output_path.exists() or output_path.stat().st_size <= 0:
            raise RuntimeError(f"stable-diffusion.cpp terminou sem gerar a imagem: {output_text[-4000:]}")

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
    quality: str = "neve_image"
    style: str = "none"


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
    quality_mode = form_data.quality == "neve_image_2"
    max_width = QUALITY_IMAGE_WIDTH if quality_mode else MAX_IMAGE_WIDTH
    max_height = QUALITY_IMAGE_HEIGHT if quality_mode else MAX_IMAGE_HEIGHT
    max_steps = QUALITY_IMAGE_STEPS if quality_mode else MAX_IMAGE_STEPS
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
        data_uri = await _sd_pipeline.run(
            model_id=model_id,
            hf_token=hf_token,
            quality=form_data.quality,
            style=form_data.style,
            prompt=form_data.prompt,
            width=width,
            height=height,
            steps=steps,
            guidance_scale=guidance_scale,
            init_image_reference=form_data.init_image,
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
