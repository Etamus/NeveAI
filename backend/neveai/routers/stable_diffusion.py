"""Shared native Qwen Image runtime and image input helpers."""

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
from neveai.utils.gpu_selection import preferred_amd_adapter, preferred_vulkan_device
from neveai.utils.image_memory import ImageGenerationError, cpu_image_requested, is_image_memory_error, monotonic_progress

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
GGUF_CACHE_DIR.mkdir(parents=True, exist_ok=True)
QWEN3_CACHE_DIR.mkdir(parents=True, exist_ok=True)
VAE_CACHE_DIR.mkdir(parents=True, exist_ok=True)

QWEN_IMAGE_21_REPO = "abenzerps/Qwen-Image-2.1-Uncensored-GGUF"
QWEN_IMAGE_21_LLM_REPO = "mradermacher/Qwen3-VL-8B-Instruct-Heretic-GGUF"
QWEN_IMAGE_21_LLM_FILE = "Qwen3-VL-8B-Instruct-heretic.Q4_K_M.gguf"
QWEN_IMAGE_21_VISION_FILE = "Qwen3-VL-8B-Instruct-heretic.mmproj-Q8_0.gguf"
QWEN_IMAGE_21_OFFICIAL_QUALITY = "qwen_image_2_1_official"
QWEN_IMAGE_2_FAST_AMD_QUALITY = "_qwen_image_2_fast_amd"
QWEN_IMAGE_TURBO_REPO = "unsloth/Qwen-Image-2.1-Turbo-GGUF"
QWEN_IMAGE_TURBO_FILE = "qwen-image-2.1-turbo-Q4_K_M.gguf"
QWEN_IMAGE_TURBO_REVISION = "5d1f9f759ea877ae556cda88dbec958b62ad3809"
QWEN_IMAGE_21_VAE_REPO = "Comfy-Org/Qwen-Image-2.1"
QWEN_IMAGE_21_VAE_FILE = "vae/qwen_image_2.1_vae_bf16.safetensors"

MAX_IMAGE_WIDTH = 768
MAX_IMAGE_HEIGHT = 768
MAX_IMAGE_STEPS = 8
QWEN_IMAGE_FAST_AMD_STEPS = 8
QWEN_IMAGE_21_OFFICIAL_STEPS = 40
QWEN_IMAGE_FAST_AMD_CFG_SCALE = 1.0
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


def normalize_image_style(value: Optional[str]) -> str:
    return "none"


def normalize_image_quality(value: Optional[str]) -> str:
    value = str(value or "qwen_image_2s").strip().lower()
    if value == "qwen_image_2_1":
        return "qwen_image_2s"
    if value == "qwen_image_2_2_experimental":
        return QWEN_IMAGE_21_OFFICIAL_QUALITY
    return value if value in {"qwen_image_2s", "minimax_h3_image", QWEN_IMAGE_21_OFFICIAL_QUALITY, QWEN_IMAGE_2_FAST_AMD_QUALITY} else "qwen_image_2s"


def normalize_qwen_image_resolution(value: Optional[str]) -> str:
    value = str(value or "1:1").strip()
    return value if value in QWEN_IMAGE_21_RESOLUTIONS else "1:1"


def qwen_image_dimensions(value: Optional[str]) -> tuple[int, int]:
    return QWEN_IMAGE_21_RESOLUTIONS[normalize_qwen_image_resolution(value)]





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
    return QWEN_IMAGE_TURBO_REPO


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






def _normalize_image_prompt_text(prompt: str) -> str:
    return re.sub(r"\s+", " ", str(prompt or "")).strip()


_QWEN_REFERENCE_GROUP_RE = re.compile(
    r"(?<!<)\b(?:imagem|imagens|image|images|fotos?|pictures?|refer[eê]ncias?|references?)\s+"
    r"((?:#?\s*\d+)(?:\s*(?:,|e|and|&)\s*#?\s*\d+)*)",
    flags=re.IGNORECASE,
)


def _normalize_qwen_reference_tokens(prompt: str, reference_count: int, *, preserve_formatting: bool = False) -> str:
    """Map reference numbers, optionally retaining instruction and literal-text formatting."""
    prompt = str(prompt or "").strip() if preserve_formatting else _normalize_image_prompt_text(prompt)
    if not prompt or reference_count <= 0:
        return prompt

    def replace_group(match: re.Match[str]) -> str:
        number_group = match.group(1)

        def replace_number(number_match: re.Match[str]) -> str:
            index = int(number_match.group(0))
            return f"<image{index}>" if 1 <= index <= reference_count else number_match.group(0)

        return re.sub(r"\d+", replace_number, number_group)

    normalized = _QWEN_REFERENCE_GROUP_RE.sub(replace_group, prompt)
    referenced = {
        int(value)
        for value in re.findall(r"<image(\d+)>", normalized, flags=re.IGNORECASE)
        if 1 <= int(value) <= reference_count
    }
    missing = [f"<image{index}>" for index in range(1, reference_count + 1) if index not in referenced]
    if missing:
        normalized = f"Reference images in attachment order: {', '.join(missing)}. {normalized}"
    return normalized


def _short_log_prompt(prompt: str, limit: int = 500) -> str:
    prompt = _normalize_image_prompt_text(prompt)
    return prompt if len(prompt) <= limit else f"{prompt[:limit]}..."
















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






@dataclass(frozen=True)
class _NativeImageResources:
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
        try:
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
                capture_output=True, text=True, timeout=10, check=False,
                **({"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}),
            )
            if result.returncode == 0 and result.stdout.strip():
                return "cuda12"
        except (OSError, subprocess.SubprocessError):
            pass
    if os.name == "nt" and preferred_amd_adapter():
        return "vulkan"
    return "cpu"


def _detected_gpu_vram_mib(*, selected_only: bool = False) -> Optional[int]:
    """Return conservative dedicated VRAM detection for memory-policy selection."""
    backend = _preferred_sd_cpp_windows_backend() if os.name == "nt" else "cuda12" if shutil.which("nvidia-smi") else "cpu"
    if backend == "cuda12":
        try:
            result = subprocess.run(
                [
                    "nvidia-smi",
                    *(["--id=" + (os.environ.get("CUDA_VISIBLE_DEVICES") or "0").split(",")[0].strip()] if selected_only else []),
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

    if os.name == "nt" and backend == "vulkan":
        adapter = preferred_amd_adapter()
        if adapter:
            try:
                value = int(adapter.get("AdapterRAM") or 0)
                return value // (1024 * 1024) if value > 0 else None
            except (TypeError, ValueError):
                return None

    return None








def _qwen_image_memory_args() -> list[str]:
    vram_mib = _detected_gpu_vram_mib()
    if os.name == "nt" and _preferred_sd_cpp_windows_backend() == "vulkan":
        device = (preferred_vulkan_device(SD_CLI_PATH) or "vulkan0").lower()
        if vram_mib is not None and vram_mib >= QWEN_IMAGE_21_FULL_GPU_MIN_VRAM_MIB:
            log.info("Qwen Image 2.1 Vulkan: auto-fit em %s (%s MiB de VRAM detectados)", device, vram_mib)
            return ["--backend", device, "--auto-fit", "on", "--vae-tiling"]
        tight_eight_gib = False
        if vram_mib is None:
            budget = "-2"
        else:
            vram_gib = vram_mib / 1024
            tight_eight_gib = 7.5 <= vram_gib <= 8.5
            if tight_eight_gib:
                budget = f"{min(vram_gib - 1.75, vram_gib * 0.8):g}"
            else:
                budget = f"{max(0.75, min(vram_gib - 2, vram_gib * 0.7)):g}"
        log.info("Qwen Image 2.1 Vulkan: difusao limitada a %s GiB de VRAM (detectada: %s MiB)", budget, vram_mib)
        return [
            "--backend", f"te=cpu,vae=cpu,diffusion={device}",
            "--auto-fit", "on",
            "--max-vram", budget, "--vae-tiling",
            *(["--disable-prefetch"] if tight_eight_gib else []),
        ]
    if vram_mib is not None and vram_mib >= QWEN_IMAGE_21_FULL_GPU_MIN_VRAM_MIB:
        log.info("Qwen Image 2.1: auto-fit em GPU (%s MiB de VRAM detectados)", vram_mib)
        return ["--auto-fit", "on", "--vae-tiling"]

    detected = f"{vram_mib} MiB" if vram_mib is not None else "desconhecida"
    log.info("Qwen Image 2.1: offload conservador (VRAM %s)", detected)
    return ["--offload-to-cpu", "--vae-tiling"]


def _qwen_image_cpu_fallback_command(command: list[str]) -> list[str]:
    memory_start = command.index("--auto-fit", command.index("--cfg-scale") + 2)
    if "--backend" in command[command.index("--cfg-scale") + 2:memory_start]:
        memory_start = command.index("--backend", command.index("--cfg-scale") + 2)
    memory_end = command.index("--vae-tiling", memory_start) + 1
    return command[:memory_start] + ["--backend", "cpu", "--auto-fit", "off", "--vae-tiling"] + command[memory_end:]


def _is_vulkan_memory_failure(output: str) -> bool:
    return bool(re.search(
        r"ErrorDeviceLost|device lost|ErrorOutOfDeviceMemory|cannot make enough memory available|"
        r"failed during weight preparation|out of memory",
        output,
        re.IGNORECASE,
    ))


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


class _NativeQwenPipeline:
    """Gerencia os runtimes locais de imagem e executa sd-cli em serie."""

    def __init__(self):
        self._resources: Optional[_NativeImageResources] = None
        self._model_id: Optional[str] = None
        self._quality = '_qwen_image_2_fast_amd'
        self._edit_mode = False
        self._force_cpu = False
        self._recovery_seed = None
        self._retry_prepared_prompt = None
        self._recovery_lock = asyncio.Lock()
        self._load_lock = asyncio.Lock()
        self._generation_lock = asyncio.Lock()
        self._request_lock = asyncio.Lock()

    @property
    def is_loaded(self) -> bool:
        return self._resources is not None

    async def load(self, model_id: str, device: str='cuda', hf_token: Optional[str]=None, quality: str=QWEN_IMAGE_2_FAST_AMD_QUALITY, edit: bool=False):
        async with self._load_lock:
            if normalize_image_quality(quality) != QWEN_IMAGE_2_FAST_AMD_QUALITY:
                raise ValueError('Este runtime nativo atende somente o Qwen Image para AMD.')
            model_id = normalize_sd_model_id(model_id)
            if self._resources is not None and self._model_id == model_id and (self._quality == '_qwen_image_2_fast_amd') and (self._edit_mode == edit):
                return
            loop = asyncio.get_event_loop()

            def _prepare_sync() -> _NativeImageResources:
                from huggingface_hub import hf_hub_download
                sd_cli = _ensure_sd_cli_binary(require_qwen_image_21=True)
                token = hf_token or None

                def download_qwen(repo: str, filename: str, cache_dir: Path, revision: Optional[str]=None) -> Path:
                    return Path(hf_hub_download(repo_id=repo, filename=filename, cache_dir=str(cache_dir), token=token, revision=revision))
                log.info('Baixando/carregando Neve Image 2 Turbo Q4_K_M para AMD Vulkan...')
                return _NativeImageResources(sd_cli=sd_cli, diffusion_model=download_qwen(QWEN_IMAGE_TURBO_REPO, QWEN_IMAGE_TURBO_FILE, GGUF_CACHE_DIR, QWEN_IMAGE_TURBO_REVISION), llm=download_qwen(QWEN_IMAGE_21_LLM_REPO, QWEN_IMAGE_21_LLM_FILE, QWEN3_CACHE_DIR), vae=download_qwen(QWEN_IMAGE_21_VAE_REPO, QWEN_IMAGE_21_VAE_FILE, VAE_CACHE_DIR), llm_vision=download_qwen(QWEN_IMAGE_21_LLM_REPO, QWEN_IMAGE_21_VISION_FILE, QWEN3_CACHE_DIR) if edit else None)
            self._resources = await loop.run_in_executor(None, _prepare_sync)
            self._model_id = model_id
            self._quality = '_qwen_image_2_fast_amd'
            self._edit_mode = edit
            runtime_name = 'Neve Image 2 (AMD)'
            log.info('%s pronto via stable-diffusion.cpp', runtime_name)

    async def unload(self):
        async with self._request_lock:
            async with self._load_lock:
                self._resources = None
                self._model_id = None
                self._quality = '_qwen_image_2_fast_amd'
                self._edit_mode = False

    async def run(self, model_id: str, hf_token: Optional[str], quality: str, style: str='none', progress_callback: Optional[ImageProgressCallback]=None, dimensions_callback: Optional[ImageDimensionsCallback]=None, **kwargs) -> str:
        async with self._recovery_lock:
            cpu = os.name == 'nt' and cpu_image_requested(await asyncio.to_thread(_preferred_sd_cpp_windows_backend))
            plans = [True] if cpu else [False, False, True]
            report = monotonic_progress(progress_callback)
            self._recovery_seed = random.randint(0, 2 ** 31 - 1)
            self._retry_prepared_prompt = None
            try:
                for index, force_cpu in enumerate(plans):
                    self._force_cpu = force_cpu
                    try:
                        return await self._run_once(model_id, hf_token, '_qwen_image_2_fast_amd', style, report, dimensions_callback, **kwargs)
                    except Exception as exc:
                        if not is_image_memory_error(exc) or index == len(plans) - 1:
                            raise
                        log.warning('Imagem local: recuperacao de memoria, tentativa %s: %s', index + 2, exc)
                        await self.unload()
            finally:
                self._force_cpu = False
                self._recovery_seed = self._retry_prepared_prompt = None

    async def _run_once(self, model_id: str, hf_token: Optional[str], quality: str, style: str='none', progress_callback: Optional[ImageProgressCallback]=None, dimensions_callback: Optional[ImageDimensionsCallback]=None, **kwargs) -> str:
        async with self._request_lock:
            quality = normalize_image_quality('_qwen_image_2_fast_amd')
            style = 'none'
            has_reference = bool(kwargs.get('init_image_references') or kwargs.get('init_image_reference'))
            needs_vision = has_reference
            load_task = asyncio.create_task(self.load(model_id, hf_token=hf_token, quality='_qwen_image_2_fast_amd', edit=needs_vision))
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
            return await self.generate(hf_token=hf_token, style=style, progress_callback=progress_callback, dimensions_callback=dimensions_callback, **kwargs)

    async def generate(self, prompt: str, width: int=MAX_IMAGE_WIDTH, height: int=MAX_IMAGE_HEIGHT, steps: int=MAX_IMAGE_STEPS, guidance_scale: float=DEFAULT_CFG_SCALE, init_image_reference: Optional[str]=None, init_image_references: Optional[list[str]]=None, resolution: str='1:1', user_id: Optional[str]=None, hf_token: Optional[str]=None, style: str='none', progress_callback: Optional[ImageProgressCallback]=None, dimensions_callback: Optional[ImageDimensionsCallback]=None) -> str:
        if not self.is_loaded or self._resources is None:
            raise RuntimeError('Runtime local de imagem nao carregado')
        if progress_callback is not None:
            await progress_callback(22)
        prompt = (self._retry_prepared_prompt if self._recovery_seed is not None else None) or _normalize_image_prompt_text(prompt)
        if not prompt:
            raise RuntimeError('Prompt vazio para geracao de imagem')
        if self._recovery_seed is not None:
            self._retry_prepared_prompt = prompt
        if progress_callback is not None:
            await progress_callback(26)
        style = 'none'
        if progress_callback is not None:
            await progress_callback(30)
        reference_values = list(init_image_references or [])
        if init_image_reference and init_image_reference not in reference_values:
            reference_values.insert(0, init_image_reference)
        reference_images = await _prepare_reference_images(reference_values, user_id=user_id)
        width, height = qwen_image_dimensions(resolution)
        if dimensions_callback is not None:
            await dimensions_callback(width, height)
        if progress_callback is not None:
            await progress_callback(33)
        steps = QWEN_IMAGE_FAST_AMD_STEPS
        cfg = QWEN_IMAGE_FAST_AMD_CFG_SCALE
        seed = self._recovery_seed if self._recovery_seed is not None else random.randint(0, 2 ** 31 - 1)
        filename = f'sd_{int(time.time())}_{seed}.png'
        output_path = IMAGE_OUTPUT_DIR / filename
        log.info('Prompt final enviado ao sd-cli (seed=%s): %s', seed, _short_log_prompt(prompt))
        attention_args = [] if self._force_cpu else ['--sage-attn'] if _supports_native_sage_attention() else ['--diffusion-fa']
        cmd = [str(self._resources.sd_cli), '--diffusion-model', str(self._resources.diffusion_model), '--llm', str(self._resources.llm), '--vae', str(self._resources.vae), '-p', prompt, '-W', str(width), '-H', str(height), '--steps', str(steps), '--cfg-scale', f'{cfg:g}', *attention_args, *(_qwen_image_memory_args() if not self._force_cpu else []), *(['--backend', 'cpu', '--auto-fit', 'off', '--vae-tiling', '--mmap'] if self._force_cpu else []), *(['--llm_vision', str(self._resources.llm_vision)] if self._resources.llm_vision is not None else []), *['--sampling-method', 'euler'], '-s', str(seed), '-o', str(output_path)]
        from neveai.routers.image_fast_generation import SIGMAS
        cmd.extend(['--sigmas', SIGMAS])
        for reference_image in reference_images:
            cmd.extend(['-r', str(reference_image.path)])
        if reference_images:
            cmd.extend(['--ref-image-args', 'preset=qwen'])
        env = os.environ.copy()
        env['PATH'] = f"{SD_CPP_DIR}{os.pathsep}{env.get('PATH', '')}"
        try:
            async with self._generation_lock:
                has_input = bool(reference_images)
                mode = 'image-edit' if has_input else 'txt2img'
                runtime_name = 'Qwen Image 2.1'
                log.info('Gerando imagem %s %s %sx%s, steps=%s, cfg=%s', runtime_name, mode, width, height, steps, cfg)
                last_progress = 33
                retry_on_cpu = not self._force_cpu and os.name == 'nt' and (_preferred_sd_cpp_windows_backend() == 'vulkan')
                commands = [cmd]
                if retry_on_cpu:
                    commands.append(_qwen_image_cpu_fallback_command(cmd))
                for attempt, command in enumerate(commands):
                    process = await asyncio.create_subprocess_exec(*command, cwd=str(SD_CPP_DIR), env=env, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, **{'creationflags': subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {})
                    stdout_chunks: list[bytes] = []
                    stderr_chunks: list[bytes] = []

                    async def read_stream(stream: Optional[asyncio.StreamReader], chunks: list[bytes]) -> None:
                        nonlocal last_progress
                        if stream is None:
                            return
                        carry = ''
                        while True:
                            chunk = await stream.read(2048)
                            if not chunk:
                                break
                            chunks.append(chunk)
                            carry = (carry + chunk.decode('utf-8', errors='replace'))[-1024:]
                            for match in re.finditer('(?<!\\d)(\\d+)\\s*/\\s*(\\d+)(?!\\d)', carry):
                                current = int(match.group(1))
                                total = int(match.group(2))
                                if total != steps or current < 0 or current > total:
                                    continue
                                percent = min(91, max(34, 34 + round(current / total * 57)))
                                if percent <= last_progress:
                                    continue
                                last_progress = percent
                                if progress_callback is not None:
                                    try:
                                        await progress_callback(percent)
                                    except Exception as exc:
                                        log.debug('Image progress callback failed: %s', exc)

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
                                            log.debug('Image progress pulse failed: %s', exc)
                        await asyncio.gather(read_stream(process.stdout, stdout_chunks), read_stream(process.stderr, stderr_chunks), process.wait(), pulse_progress())
                    try:
                        await asyncio.wait_for(communicate_with_progress(), timeout=SD_CLI_TIMEOUT_SECONDS)
                    except asyncio.CancelledError:
                        if process.returncode is None:
                            process.kill()
                            await process.wait()
                        raise
                    except asyncio.TimeoutError:
                        process.kill()
                        await process.wait()
                        raise RuntimeError('Geracao de imagem excedeu o tempo limite do stable-diffusion.cpp')
                    output = b''.join(stdout_chunks) + b'\n' + b''.join(stderr_chunks)
                    output_text = output.decode('utf-8', errors='replace')
                    if process.returncode == 0:
                        break
                    diagnostic = output_text.replace(prompt, '<prompt>')
                    if attempt == 0 and retry_on_cpu and _is_vulkan_memory_failure(diagnostic):
                        log.warning('Qwen Image 2.1: falha de memoria no Vulkan; repetindo esta geracao em CPU')
                        continue
                    raise ImageGenerationError(f'stable-diffusion.cpp falhou (codigo {process.returncode}): {output_text[-4000:]}', memory_failure=is_image_memory_error(diagnostic))
        finally:
            temporary_images = [*reference_images]
            for temporary_image in temporary_images:
                try:
                    temporary_image.path.unlink(missing_ok=True)
                except TypeError:
                    if temporary_image.path.exists():
                        temporary_image.path.unlink()
                except Exception as e:
                    log.debug('Nao foi possivel remover imagem temporaria de referencia: %s', e)
        if not output_path.exists() or output_path.stat().st_size <= 0:
            raise RuntimeError(f'stable-diffusion.cpp terminou sem gerar a imagem: {output_text[-4000:]}')
        if progress_callback is not None:
            await progress_callback(99)
        raw = output_path.read_bytes()
        b64 = base64.b64encode(raw).decode('utf-8')
        return f'data:image/png;base64,{b64}'


_sd_pipeline = _NativeQwenPipeline()


class GenerateForm(BaseModel):
    prompt: str
    width: Optional[int] = None
    height: Optional[int] = None
    steps: Optional[int] = None
    guidance_scale: Optional[float] = None
    init_image: Optional[str] = None
    init_images: Optional[list[str]] = None
    quality: str = "qwen_image_2s"
    style: str = "none"
    resolution: str = "1:1"
    mode_options: Optional[dict] = None


@router.post("/modes/segment")
async def segment_mode_image(request: Request, user=Depends(get_verified_user)):
    if not request.app.state.config.ENABLE_STABLE_DIFFUSION or (
        user.role != "admin" and not has_permission(user.id, "features.stable_diffusion", request.app.state.config.USER_PERMISSIONS)
    ):
        raise HTTPException(status_code=403, detail="Geracao de imagem indisponivel.")
    from neveai.routers.image_fast_modes import SegmentRequest, segment_image
    from pydantic import ValidationError
    try:
        form = SegmentRequest.model_validate(await request.json())
    except (ValidationError, ValueError) as exc:
        raise HTTPException(status_code=422, detail="Selecao invalida.") from exc
    task = None
    watcher = None
    async def cancel_on_disconnect():
        while True:
            await asyncio.sleep(0.2)
            if await request.is_disconnected():
                if task is not None:
                    task.cancel()
                return
    try:
        task = asyncio.create_task(segment_image(form, user.id))
        watcher = asyncio.create_task(cancel_on_disconnect())
        return {"mask": await task}
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        if watcher is not None:
            watcher.cancel()
            await asyncio.gather(watcher, return_exceptions=True)


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
    qwen_image_mode = quality in {QWEN_IMAGE_2_FAST_AMD_QUALITY, QWEN_IMAGE_21_OFFICIAL_QUALITY}
    max_width = MAX_IMAGE_WIDTH
    max_height = MAX_IMAGE_HEIGHT
    max_steps = MAX_IMAGE_STEPS
    if qwen_image_mode or quality == "qwen_image_2s":
        width, height = qwen_image_dimensions(form_data.resolution)
        steps = (
            8 if quality == "qwen_image_2s"
            else QWEN_IMAGE_21_OFFICIAL_STEPS if quality == QWEN_IMAGE_21_OFFICIAL_QUALITY
            else QWEN_IMAGE_FAST_AMD_STEPS
        )
    else:
        width = _align_image_dim(form_data.width or request.app.state.config.STABLE_DIFFUSION_WIDTH, max_width, max_width)
        height = _align_image_dim(form_data.height or request.app.state.config.STABLE_DIFFUSION_HEIGHT, max_height, max_height)
        steps = _clamp_int(form_data.steps or request.app.state.config.STABLE_DIFFUSION_STEPS, max_steps, 1, max_steps)
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
        if quality == "minimax_h3_image":
            from neveai.routers.image_h3_generation import neve_image_3_runtime

            references = list(form_data.init_images or [])
            if form_data.init_image and form_data.init_image not in references:
                references.insert(0, form_data.init_image)
            data_uri = await neve_image_3_runtime.run(
                prompt=form_data.prompt, resolution=form_data.resolution, references=references,
                user_id=getattr(user, "id", None), progress=lambda _: asyncio.sleep(0),
            )
        elif quality == QWEN_IMAGE_21_OFFICIAL_QUALITY:
            from neveai.routers.image_quality_generation import neve_image_21_runtime

            runtime = neve_image_21_runtime

            references = list(form_data.init_images or [])
            if form_data.init_image and form_data.init_image not in references:
                references.insert(0, form_data.init_image)
            data_uri = await runtime.run(
                prompt=form_data.prompt,
                resolution=form_data.resolution,
                references=references,
                user_id=getattr(user, "id", None),
                progress=lambda _: asyncio.sleep(0),
            )
        elif quality == "qwen_image_2s":
            from neveai.routers.image_fast_generation import neve_image_2s_runtime

            references = list(form_data.init_images or [])
            if form_data.init_image and form_data.init_image not in references:
                references.insert(0, form_data.init_image)
            image_runner = neve_image_2s_runtime.run
            if form_data.mode_options and form_data.mode_options.get("mode", "normal") != "normal":
                from neveai.routers.image_fast_modes import run_image_mode
                from functools import partial
                image_runner = partial(run_image_mode, options=form_data.mode_options)
            data_uri = await image_runner(
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
