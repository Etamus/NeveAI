"""
Z-Image-Turbo local -- geracao de imagem via stable-diffusion.cpp.

O runtime usa o diffusion model GGUF do Z-Image-Turbo, Qwen3-4B como text
encoder e o VAE do FLUX.1-schnell, conforme suporte oficial do sd-cli.

Resolucao: 768 x 768
Steps    : 8
Modelo   : leejet/Z-Image-Turbo-GGUF / z_image_turbo-Q4_0.gguf
"""

import asyncio
import base64
import fnmatch
import io
import json
import logging
import os
import random
import re
import time
import urllib.parse
import urllib.request
import zipfile
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from neveai.config import CACHE_DIR, STABLE_DIFFUSION_HF_TOKEN
from neveai.constants import ERROR_MESSAGES
from neveai.utils.access_control import has_permission
from neveai.utils.auth import get_admin_user, get_verified_user

log = logging.getLogger(__name__)
router = APIRouter()

BACKEND_DIR = Path(__file__).resolve().parents[2]
SD_CPP_DIR = BACKEND_DIR / "bin" / "stable-diffusion-cpp"
SD_CLI_PATH = SD_CPP_DIR / ("sd-cli.exe" if os.name == "nt" else "sd-cli")
SD_CPP_RELEASE_API = "https://api.github.com/repos/leejet/stable-diffusion.cpp/releases/latest"
SD_CPP_WIN_CUDA_ASSET = "sd-*-bin-win-cuda12-x64.zip"
SD_CPP_WIN_CUDART_ASSET = "cudart-sd-bin-win-cu12-x64.zip"
SD_CLI_TIMEOUT_SECONDS = 60 * 60

IMAGE_OUTPUT_DIR = CACHE_DIR / "image" / "generations"
IMAGE_INPUT_DIR = CACHE_DIR / "image" / "inputs"
IMAGE_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
IMAGE_INPUT_DIR.mkdir(parents=True, exist_ok=True)

SD_CACHE_DIR = CACHE_DIR / "stable_diffusion"
GGUF_CACHE_DIR = SD_CACHE_DIR / "gguf"
QWEN3_CACHE_DIR = SD_CACHE_DIR / "qwen3"
VAE_CACHE_DIR = SD_CACHE_DIR / "vae"
GGUF_CACHE_DIR.mkdir(parents=True, exist_ok=True)
QWEN3_CACHE_DIR.mkdir(parents=True, exist_ok=True)
VAE_CACHE_DIR.mkdir(parents=True, exist_ok=True)

ZIMAGE_REPO = "leejet/Z-Image-Turbo-GGUF"
ZIMAGE_GGUF_FILE = "z_image_turbo-Q4_0.gguf"
QWEN3_LLM_REPO = "unsloth/Qwen3-4B-Instruct-2507-GGUF"
QWEN3_LLM_FILE = "Qwen3-4B-Instruct-2507-Q4_K_M.gguf"
ZIMAGE_VAE_REPO = "black-forest-labs/FLUX.1-schnell"
ZIMAGE_VAE_FILE = "ae.safetensors"

MAX_IMAGE_WIDTH = 768
MAX_IMAGE_HEIGHT = 768
MAX_IMAGE_STEPS = 8
DEFAULT_CFG_SCALE = 1.0
DEFAULT_IMG2IMG_STRENGTH = 0.55
MAX_INIT_IMAGE_BYTES = 30 * 1024 * 1024
IMAGE_PROMPT_TRANSLATION_TIMEOUT_SECONDS = 20.0
IMAGE_PROMPT_TRANSLATION_CHUNK_CHARS = 4500

_PORTUGUESE_MARKERS = {
    "quero", "gere", "gerar", "crie", "criar", "desenhe", "faça", "faca",
    "imagem", "foto", "retrato", "realista", "cinematografico", "cinematográfico",
    "com", "sem", "para", "sobre", "baixo", "alto", "dentro", "fora",
    "homem", "mulher", "menino", "menina", "pessoa", "cachorro", "gato",
    "cidade", "praia", "floresta", "montanha", "ceu", "céu", "noite", "dia",
    "rua", "câmera", "camera", "granulada", "granulado", "iluminacao", "iluminação",
    "vermelho", "azul", "verde", "amarelo", "preto", "branco", "luz",
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


def _fit_init_image_dimensions(init_image: _InitImage, max_width: int, max_height: int) -> tuple[int, int]:
    max_width = _align_image_dim(max_width, MAX_IMAGE_WIDTH, MAX_IMAGE_WIDTH)
    max_height = _align_image_dim(max_height, MAX_IMAGE_HEIGHT, MAX_IMAGE_HEIGHT)

    if init_image.width <= 0 or init_image.height <= 0:
        return max_width, max_height

    scale = min(max_width / init_image.width, max_height / init_image.height)
    width = int(init_image.width * scale)
    height = int(init_image.height * scale)
    width = max(256, min(max_width, (width // 16) * 16))
    height = max(256, min(max_height, (height // 16) * 16))
    return width, height


def _looks_portuguese(text: str) -> bool:
    if _PORTUGUESE_ACCENT_RE.search(text):
        return True
    words = {word.lower() for word in _WORD_RE.findall(text)}
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


def _split_prompt_for_translation(prompt: str) -> list[str]:
    prompt = _normalize_image_prompt_text(prompt)
    if len(prompt) <= IMAGE_PROMPT_TRANSLATION_CHUNK_CHARS:
        return [prompt]

    chunks: list[str] = []
    current: list[str] = []
    current_len = 0

    for sentence in _SENTENCE_SPLIT_RE.split(prompt):
        sentence = sentence.strip()
        if not sentence:
            continue

        if len(sentence) > IMAGE_PROMPT_TRANSLATION_CHUNK_CHARS:
            if current:
                chunks.append(" ".join(current).strip())
                current = []
                current_len = 0
            for start in range(0, len(sentence), IMAGE_PROMPT_TRANSLATION_CHUNK_CHARS):
                chunks.append(sentence[start : start + IMAGE_PROMPT_TRANSLATION_CHUNK_CHARS].strip())
            continue

        next_len = current_len + len(sentence) + (1 if current else 0)
        if current and next_len > IMAGE_PROMPT_TRANSLATION_CHUNK_CHARS:
            chunks.append(" ".join(current).strip())
            current = [sentence]
            current_len = len(sentence)
        else:
            current.append(sentence)
            current_len = next_len

    if current:
        chunks.append(" ".join(current).strip())
    return [chunk for chunk in chunks if chunk]


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


@lru_cache(maxsize=512)
def _translate_image_prompt_sync(prompt: str) -> str:
    prompt = _normalize_image_prompt_text(prompt)
    if not prompt:
        return prompt

    try:
        from deep_translator import GoogleTranslator
    except Exception as e:
        raise RuntimeError(f"deep-translator nao carregou: {e}") from e

    try:
        source_language = "pt" if _looks_portuguese(prompt) else "auto"
        translator = GoogleTranslator(source=source_language, target="en")
        translated_chunks = []
        for chunk in _split_prompt_for_translation(prompt):
            translated = translator.translate(chunk)
            translated = _normalize_image_prompt_text(str(translated or ""))
            if translated:
                translated_chunks.append(translated)
    except Exception as e:
        raise RuntimeError(f"falha ao traduzir prompt de imagem: {e}") from e

    return _polish_translated_image_prompt(" ".join(translated_chunks), prompt) or prompt


async def _prepare_image_prompt(prompt: str) -> str:
    prompt = _normalize_image_prompt_text(prompt)
    if not prompt:
        return prompt

    if _looks_english(prompt):
        log.info(
            "Prompt de imagem ja esta em ingles; usando sem traducao: %s",
            _short_log_prompt(prompt),
        )
        return prompt

    loop = asyncio.get_event_loop()
    try:
        translated = await asyncio.wait_for(
            loop.run_in_executor(None, _translate_image_prompt_sync, prompt),
            timeout=IMAGE_PROMPT_TRANSLATION_TIMEOUT_SECONDS,
        )
    except Exception as e:
        if _looks_english(prompt) and not _looks_portuguese(prompt):
            log.warning("Traducao de prompt em ingles falhou; usando original: %s", e)
            return prompt
        raise RuntimeError(
            "Nao foi possivel traduzir o prompt de imagem para ingles. "
            "Verifique a conexao do deep-translator e tente novamente."
        ) from e

    translated = _normalize_image_prompt_text(translated)
    if not translated:
        raise RuntimeError("Traducao do prompt de imagem retornou vazia")

    if translated != prompt:
        log.info(
            "Prompt de imagem traduzido para ingles antes da geracao: %s",
            _short_log_prompt(translated),
        )
    else:
        log.info("Prompt de imagem confirmado em ingles antes da geracao")
    return translated


@dataclass(frozen=True)
class _ZImageResources:
    sd_cli: Path
    diffusion_model: Path
    llm: Path
    vae: Path


def _download_file(url: str, destination: Path):
    destination.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(url, headers={"User-Agent": "NeveAI/1.0"})
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


def _ensure_sd_cli_binary() -> Path:
    if SD_CLI_PATH.exists():
        return SD_CLI_PATH

    if os.name != "nt":
        raise RuntimeError(
            "sd-cli nao foi encontrado. Instale stable-diffusion.cpp e coloque o binario em "
            f"{SD_CLI_PATH}."
        )

    SD_CPP_DIR.mkdir(parents=True, exist_ok=True)
    log.info("sd-cli nao encontrado; baixando stable-diffusion.cpp CUDA 12 para Windows...")
    request = urllib.request.Request(SD_CPP_RELEASE_API, headers={"User-Agent": "NeveAI/1.0"})
    with urllib.request.urlopen(request, timeout=60) as response:
        release = json.loads(response.read().decode("utf-8"))

    assets = release.get("assets") or []
    sd_asset = next((asset for asset in assets if fnmatch.fnmatch(asset.get("name", ""), SD_CPP_WIN_CUDA_ASSET)), None)
    cudart_asset = next((asset for asset in assets if asset.get("name") == SD_CPP_WIN_CUDART_ASSET), None)
    if not sd_asset or not cudart_asset:
        raise RuntimeError("Release do stable-diffusion.cpp nao contem binarios Windows CUDA 12 esperados")

    _download_and_extract_sd_cpp_asset(sd_asset)
    _download_and_extract_sd_cpp_asset(cudart_asset)
    if not SD_CLI_PATH.exists():
        raise RuntimeError(f"sd-cli nao foi extraido corretamente em {SD_CLI_PATH}")
    return SD_CLI_PATH


class _ZImageTurboPipeline:
    """Gerencia os recursos Z-Image-Turbo e executa sd-cli de forma serializada."""

    def __init__(self):
        self._resources: Optional[_ZImageResources] = None
        self._model_id: Optional[str] = None
        self._load_lock = asyncio.Lock()
        self._generation_lock = asyncio.Lock()

    @property
    def is_loaded(self) -> bool:
        return self._resources is not None

    async def load(self, model_id: str, device: str = "cuda", hf_token: Optional[str] = None):
        async with self._load_lock:
            model_id = normalize_sd_model_id(model_id)
            if self._resources is not None and self._model_id == model_id:
                return

            loop = asyncio.get_event_loop()

            def _prepare_sync() -> _ZImageResources:
                from huggingface_hub import hf_hub_download

                sd_cli = _ensure_sd_cli_binary()
                token = hf_token or None

                log.info("Baixando/carregando Z-Image-Turbo Q4_0 GGUF...")
                diffusion_model = Path(
                    hf_hub_download(
                        repo_id=model_id,
                        filename=ZIMAGE_GGUF_FILE,
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

                log.info("Baixando/carregando VAE FLUX.1-schnell...")
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
            log.info("Z-Image-Turbo pronto via stable-diffusion.cpp")

    async def unload(self):
        async with self._load_lock:
            self._resources = None
            self._model_id = None

    async def generate(
        self,
        prompt: str,
        width: int = MAX_IMAGE_WIDTH,
        height: int = MAX_IMAGE_HEIGHT,
        steps: int = MAX_IMAGE_STEPS,
        guidance_scale: float = DEFAULT_CFG_SCALE,
        init_image_reference: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> str:
        if not self.is_loaded or self._resources is None:
            raise RuntimeError("Z-Image image runtime nao carregado")

        prompt = await _prepare_image_prompt(prompt)
        if not prompt:
            raise RuntimeError("Prompt vazio para geracao de imagem")

        init_image = await _prepare_init_image(init_image_reference, user_id=user_id)

        width = _align_image_dim(width, MAX_IMAGE_WIDTH, MAX_IMAGE_WIDTH)
        height = _align_image_dim(height, MAX_IMAGE_HEIGHT, MAX_IMAGE_HEIGHT)
        if init_image is not None:
            width, height = _fit_init_image_dimensions(init_image, width, height)
        steps = _clamp_int(steps, MAX_IMAGE_STEPS, 1, MAX_IMAGE_STEPS)
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
            "--offload-to-cpu",
            "-s",
            str(seed),
            "-o",
            str(output_path),
        ]
        if init_image is not None:
            cmd.extend(
                [
                    "--init-img",
                    str(init_image.path),
                    "--strength",
                    f"{DEFAULT_IMG2IMG_STRENGTH:g}",
                ]
            )

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
                try:
                    stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=SD_CLI_TIMEOUT_SECONDS)
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

        output = (stdout or b"") + b"\n" + (stderr or b"")
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
    width = _align_image_dim(
        form_data.width or request.app.state.config.STABLE_DIFFUSION_WIDTH, MAX_IMAGE_WIDTH, MAX_IMAGE_WIDTH
    )
    height = _align_image_dim(
        form_data.height or request.app.state.config.STABLE_DIFFUSION_HEIGHT, MAX_IMAGE_HEIGHT, MAX_IMAGE_HEIGHT
    )
    steps = _clamp_int(form_data.steps or request.app.state.config.STABLE_DIFFUSION_STEPS, MAX_IMAGE_STEPS, 1, MAX_IMAGE_STEPS)
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
        await _sd_pipeline.load(model_id, hf_token=hf_token)
        data_uri = await _sd_pipeline.generate(
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
