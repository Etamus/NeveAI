"""Local Pixal3D inference through the pinned native ComfyUI worker."""
import asyncio
import io
import json
import os
import random
import sys
import tempfile
from pathlib import Path

import aiohttp
import httpx
from PIL import Image, ImageOps
from neveai.utils.pinned_media_asset import ensure_pinned_asset
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask

from neveai.config import CACHE_DIR
from neveai.routers import image_fast_generation as fast
from neveai.routers.stable_diffusion import _file_id_from_image_reference, _read_image_reference_bytes
from neveai.utils.auth import get_verified_user

ROOT = CACHE_DIR / "mesh_generation"
ASSETS = {
    "Comfy-Org/Pixal3D": ("f37641be376725d324c56626007cc477f1249a69", (
        "diffusion_models/pixal3d_int8_convrot.safetensors",
        "vae/trellis_2_shape_vae_bf16.safetensors", "vae/trellis_2_texture_vae_bf16.safetensors",
        "clip_vision/dino_v3_L_naf_fp32.safetensors")),
    "Comfy-Org/MoGe": ("1484985258ba7ef45c314144fcf0e90924ffbf44", (
        "geometry_estimation/moge_2_vitl_normal_fp16.safetensors",)),
    "Comfy-Org/BiRefNet": ("884af709e9b795d89dafbf97f29c8d6a2386f5c6", (
        "background_removal/birefnet.safetensors",)),
}


MESH_DIGESTS = {
    "pixal3d_int8_convrot.safetensors": (5584555824, "4621eac3b715484f79303c7152af641fe0b2b14f4d0e3d394fd6922d00f955ec"),
    "trellis_2_shape_vae_bf16.safetensors": (1095844024, "de0cb4949a76c59ee5c091a995a69bcc8c51d5aeda939f0c641a50d2a72341f4"),
    "trellis_2_texture_vae_bf16.safetensors": (948461364, "714e5ebf094a610e12a8e3b5175c18a62f37f6ea4218acb6073644456b73ab0e"),
    "dino_v3_L_naf_fp32.safetensors": (1215214176, "4ad2ec4e0879a5b5b04cd97325cc37da954a7b6edca5170b86510f17f2b2290f"),
    "moge_2_vitl_normal_fp16.safetensors": (661859924, "cb1a692d03235671e959e81360d7b4d9f44aefadb1f852d6ca6aa17799d5e31f"),
    "birefnet.safetensors": (444473596, "9ab37426bf4de0567af6b5d21b16151357149139362e6e8992021b8ce356a154"),
}


def workflow(filename, seed, *, alpha=False, compact=False):
    # Native Comfy-Org Pixal3D template, with unused switches and previews removed.
    graph = {}

    def node(name, kind, **inputs):
        graph[name] = {"class_type": kind, "inputs": inputs}
        return [name, 0]

    def sample(name, model, conditions, latent, steps, cfg, scheduler="normal"):
        return node(name, "KSampler", model=model, positive=conditions,
                    negative=[conditions[0], 1], latent_image=latent, seed=seed,
                    steps=steps, cfg=cfg, sampler_name="euler", scheduler=scheduler, denoise=1.0)

    image = node("input", "LoadImage", image=filename)
    if alpha:
        mask = node("mask", "InvertMask", mask=["input", 1])
    else:
        bg = node("bg", "LoadBackgroundRemovalModel", bg_removal_name="birefnet.safetensors")
        mask = node("mask", "RemoveBackground", bg_removal_model=bg, image=image)
    crop = node("crop", "ImageCropToMask", images=image, masks=mask, width=1024, height=1024,
                pad_factor=1.1, grow_mask=0, background="#000000")
    moge = node("moge", "LoadMoGeModel", model_name="moge_2_vitl_normal_fp16.safetensors")
    depth = node("depth", "MoGeInference", moge_model=moge, image=crop, resolution_level=9,
                 fov_x_degrees=0.0, batch_size=1, force_projection=True, apply_mask=True, refine_steps=3)
    fov = node("fov", "MoGeGeometryToFOV", moge_geometry=depth, axis="horizontal", unit="degrees")
    clip = node("clip", "CLIPVisionLoader", clip_name="dino_v3_L_naf_fp32.safetensors")
    cond = node("cond", "Pixal3DConditioning", clip_vision_model=clip, image=crop, camera_angle_x=fov)
    unet = node("unet", "UNETLoader", unet_name="pixal3d_int8_convrot.safetensors", weight_dtype="default")
    vae = node("vae", "VAELoader", vae_name="trellis_2_shape_vae_bf16.safetensors")
    texture_vae = node("texture_vae", "VAELoader", vae_name="trellis_2_texture_vae_bf16.safetensors")
    structure_cfg = node("structure_cfg", "CFGOverride", model=unet, cfg=1.0, start_percent=.667, end_percent=1.0)
    structure_rescale = node("structure_rescale", "RescaleCFG", model=structure_cfg, multiplier=.7)
    structure_model = node("structure_model", "ModelSamplingSD3", model=structure_rescale, shift=5.0)
    empty = node("empty", "EmptyTrellis2LatentStructure", batch_size=1)
    structure = sample("structure", structure_model, cond, empty, 12, 7.5)
    voxel = node("voxel", "VaeDecodeStructureTrellis2", samples=structure, vae=vae, resolution="32")
    shape = node("shape", "Trellis2ShapeStage", positive=cond, negative=["cond", 1], voxel=voxel)
    shape_cfg = node("shape_cfg", "CFGOverride", model=unet, cfg=1.0, start_percent=.769, end_percent=1.0)
    shape_model = node("shape_model", "RescaleCFG", model=shape_cfg, multiplier=.5)
    coarse = sample("coarse", shape_model, shape, ["shape", 2], 20, 7.5)
    refine = node("refine", "Trellis2UpsampleStage", positive=shape, negative=["shape", 1],
                  shape_latent=coarse, vae=vae, target_resolution=1024 if compact else 1536)
    refined = sample("refined", shape_model, refine, ["refine", 2], 12, 7.5, "simple")
    mesh = node("mesh", "VaeDecodeShapeTrellis", samples=refined, vae=vae)
    tex = node("tex", "Trellis2TextureStage", positive=refine, negative=["refine", 1], shape_latent=refined)
    tex_latent = sample("tex_latent", unet, tex, ["tex", 2], 12, 1.0)
    colors = node("colors", "VaeDecodeTextureTrellis", samples=tex_latent, vae=texture_vae,
                  shape_subdivides=["mesh", 1])
    size = 1024 if compact else 2048
    solid = node("solid", "RemeshMesh", mesh=mesh, resolution=384 if compact else 512, sign_mode="solid",
                 band=1.0, project_back=0.0, fix_poles=False, smooth_iters=0,
                 drop_small_components=.01, precluster_max_verts=20_000_000,
                 **{"sign_mode.fill": 20.0, "sign_mode.qef": False})
    reduced = node("reduced", "DecimateMesh", mesh=solid, target_face_count=85000 if compact else 160000,
                   placement_mode="midpoint")
    smooth = node("smooth", "MeshSmoothNormals", mesh=reduced, crease_angle=180.0)
    uv = node("uv", "UnwrapMesh", mesh=smooth, segmenter="pec", resolution=size, padding=2, weld_distance=.0002)
    bake = node("bake", "BakeTextureFromVoxel", mesh=uv, voxel_colors=colors, texture_size=size, reference_mesh=mesh)
    material = node("material", "ApplyTextureToMesh", mesh=uv, base_color=bake,
                    metallic=["bake", 1], roughness=["bake", 2])
    node("export", "SaveGLB", mesh=material, filename_prefix="neve-3d")
    return graph


def prepare_image(reference: str, user_id: str, destination: Path) -> bool:
    if not (reference.startswith("data:image/") or _file_id_from_image_reference(reference)):
        raise ValueError("Anexe uma imagem do seu dispositivo.")
    with Image.open(io.BytesIO(_read_image_reference_bytes(reference, user_id))) as source:
        image = ImageOps.exif_transpose(source).convert("RGBA")
        image.thumbnail((1536, 1536), Image.Resampling.LANCZOS)
        alpha = image.getchannel("A").getextrema()[0] < 255
        (image if alpha else image.convert("RGB")).save(destination)
        return alpha


class MeshRuntime(fast.NeveImage2SRuntime):
    async def prepare(self, progress):
        if os.name != "nt":
            raise RuntimeError("Criar 3D requer Windows com GPU NVIDIA nesta instalacao.")
        await fast.neve_image_2s_runtime._install(progress)
        await progress(10)
        for repo, (revision, files) in ASSETS.items():
            for filename in files:
                await asyncio.to_thread(ensure_pinned_asset, ROOT / "models", filename,
                                        *MESH_DIGESTS[Path(filename).name], [(repo, revision)])
        await progress(21)

    def _comfy_command(self):
        return [str(fast._python()), str(fast.COMFY_DIR / "main.py"), "--listen", "127.0.0.1",
                "--port", str(self._port), "--base-directory", str(ROOT), "--input-directory",
                str(self.job), "--output-directory", str(self.job), "--temp-directory",
                str(self.job / "temp"), "--user-directory", str(self.job / "user"),
                "--disable-all-custom-nodes", "--disable-auto-launch", "--disable-metadata",
                "--preview-method", "none", "--reserve-vram", "1.0"]

    async def generate(self, job: Path, alpha: bool, progress, *, compact=False):
        self.job = job
        (job / "user").mkdir(exist_ok=True)
        (job / "temp").mkdir(exist_ok=True)
        seed = random.getrandbits(63)
        stages = {"structure": 28, "coarse": 40, "refined": 56, "tex_latent": 69,
                  "solid": 80, "uv": 87, "bake": 92, "export": 98}
        try:
            base = await self._start(progress)
            async with aiohttp.ClientSession() as events, httpx.AsyncClient(base_url=base, timeout=30) as client:
                async with events.ws_connect(base.replace("http://", "ws://") + "/ws?clientId=neve-3d") as stream:
                    response = await client.post("/prompt", json={
                        "prompt": workflow("reference.png", seed, alpha=alpha, compact=compact),
                        "client_id": "neve-3d"})
                    if response.is_error or response.json().get("node_errors"):
                        raise RuntimeError(f"Workflow Pixal3D: {response.text[:1800]}")
                    prompt_id = response.json()["prompt_id"]
                    async with asyncio.timeout(900):
                        async for event in stream:
                            if event.type != aiohttp.WSMsgType.TEXT:
                                continue
                            message = event.json()
                            data = message.get("data", {})
                            if data.get("prompt_id") != prompt_id:
                                continue
                            kind = message.get("type")
                            if kind == "execution_error":
                                raise RuntimeError(data.get("exception_message") or "Pixal3D falhou")
                            if kind == "execution_success" or (kind == "executing" and data.get("node", "") is None):
                                break
                            if kind == "executing" and data.get("node") in stages:
                                await progress(stages[data["node"]])
            paths = list(job.glob("neve-3d_*.glb"))
            if len(paths) != 1:
                raise RuntimeError("Pixal3D nao retornou uma malha GLB.")
            with paths[0].open("rb") as result:
                if result.read(4) != b"glTF":
                    raise RuntimeError("GLB invalido.")
            return paths[0]
        finally:
            await self._stop()


mesh_runtime = MeshRuntime()

router = APIRouter()
export_slot = asyncio.Semaphore(1)
EXPORT_RUNTIME = ROOT / "export"
EXPORT_SCRIPT = Path(__file__).resolve().parents[1] / "utils" / "mesh_export_worker.py"


async def export_python(format, flat_base=False):
    executable = EXPORT_RUNTIME / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    digital = format in {"obj", "fbx", "blend"}
    marker = EXPORT_RUNTIME / ("blender-4.5.10.ready" if digital else
                               "print-flat-manifold-3.5.5.ready" if flat_base else "print-export-v3.ready")
    if executable.is_file() and marker.is_file():
        return executable
    if not executable.is_file():
        await mesh_runtime._command([sys.executable, "-m", "venv", str(EXPORT_RUNTIME)])
    packages = ["bpy==4.5.10"] if digital else [
        "trimesh==4.12.2", "scipy==1.15.3", "networkx==3.6.1", "point-cloud-utils==0.34.0",
    ]
    install = [str(executable), "-m", "pip", "install", "numpy==1.26.4", *packages]
    if digital:
        await mesh_runtime._command(install)
    else:
        try:
            await mesh_runtime._command([*install, "manifold3d==3.5.5"])
        except RuntimeError:
            if flat_base:
                raise
            await mesh_runtime._command(install)
        else:
            (EXPORT_RUNTIME / "print-flat-manifold-3.5.5.ready").touch()
        (EXPORT_RUNTIME / "print-export-v3.ready").touch()
    marker.touch()
    return executable


@router.get("/{file_id}/export/{format}")
async def export(file_id: str, format: str, height_mm: float = Query(100, ge=5, le=10000),
                 flat_base: bool = False,
                 user=Depends(get_verified_user)):
    from neveai.models.files import Files
    from neveai.storage.provider import Storage

    formats = {"3mf": ("3mf", "model/3mf"), "stl": ("stl", "model/stl"),
               "obj": ("zip", "application/zip"), "fbx": ("fbx", "application/octet-stream"),
               "blend": ("blend", "application/octet-stream")}
    if format not in formats:
        raise HTTPException(400, "Formato de exportacao invalido.")
    record = await asyncio.to_thread(Files.get_file_by_id_and_user_id, file_id, user.id)
    if not record or (record.meta or {}).get("data", {}).get("source") != "neve-model3d":
        raise HTTPException(404, "Modelo 3D nao encontrado.")
    source = Path(await asyncio.to_thread(Storage.get_file, record.path)).resolve()
    if not source.is_file():
        raise HTTPException(404, "Arquivo GLB nao encontrado.")
    extension, mime = formats[format]
    directory = tempfile.TemporaryDirectory(prefix="neve-mesh-export-")
    try:
        async with export_slot:
            flat_base = flat_base and format in ("3mf", "stl")
            executable = await export_python(format, flat_base)
            output = Path(directory.name) / f"modelo.{extension}"
            process = await asyncio.create_subprocess_exec(
                str(executable), str(EXPORT_SCRIPT), str(source), str(output), format,
                str(height_mm), *(["--flat-base"] if flat_base else []),
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
                **fast._process_kwargs())
            try:
                raw, _ = await asyncio.wait_for(process.communicate(), 180)
            finally:
                if process.returncode is None:
                    process.kill()
                    await process.wait()
            if process.returncode == 2:
                if b"INVALID_MESH:Flat base" in raw:
                    raise HTTPException(422, "flat_base_failed")
                raise HTTPException(422, "A malha nao forma um volume fechado para impressao.")
            if process.returncode or not output.is_file() or not output.stat().st_size:
                raise RuntimeError(raw.decode("utf-8", errors="replace")[-1500:])
        headers = {}
        if format in ("3mf", "stl"):
            line = next((line[11:] for line in raw.splitlines() if line.startswith(b"NEVE_PRINT:")), b"{}")
            checks = json.loads(line)
            if "bed_contact_mm2" in checks:
                headers["X-Neve-Bed-Contact-MM2"] = str(round(checks["bed_contact_mm2"], 4))
            if checks.get("off_balance"):
                headers["X-Neve-Print-Balance"] = "outside"
            headers["X-Neve-Print-Parts"] = str(int(checks.get("components", 0)))
            headers["X-Neve-Print-Wall"] = "unknown" if not checks or checks.get("unavailable") else "thin" if checks.get("thin") else "ok"
        return FileResponse(output, headers=headers, media_type=mime, filename=f"{Path(record.filename).stem}.{extension}",
                            background=BackgroundTask(directory.cleanup))
    except BaseException:
        directory.cleanup()
        raise
