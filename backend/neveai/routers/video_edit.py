"""Authenticated local video workspaces, analysis and cancellable exports."""
import asyncio
import base64
import hashlib
import json
import logging
import math
import os
import shutil
import re
import subprocess
import sys
import time
from threading import Event
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Literal
from uuid import UUID, uuid4
from urllib.parse import unquote

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile
from pydantic import BaseModel, Field
from starlette.responses import FileResponse, Response, StreamingResponse

from neveai.config import CACHE_DIR, WHISPER_MODEL_DIR
from neveai.utils.auth import get_verified_user
from neveai.utils.video_edit import (
    FORMATS, MAX_DURATION, MAX_CLIPS, MAX_CAPTIONS, Timeline, ffmpeg_binary, probe,
    layered, layer_slices, positioned, preview_waveform, projected_captions, render_command,
    render_layer_command, subtitle_filter, write_srt,
)
from neveai.utils.video_edit_director import direct_edit, RequestedClipTool
from neveai.utils.video_edit_model import director_model
from neveai.utils.video_edit_styles import write_intro
from neveai.utils.video_edit_weights import MODEL_NAME
from neveai.utils.video_edit_media_tools import available, process_tool, selection_frame, shot_geometry

router = APIRouter()
log = logging.getLogger(__name__)
ROOT = CACHE_DIR / "video_edit"
MAX_UPLOAD = 32 * 1024 ** 3
TTL = 3 * 24 * 3600
ACTIVE = {"queued", "exporting"}
jobs = {}
edit_operations = {}
workers = asyncio.Semaphore(1)
uploads = asyncio.Semaphore(2)
analysis_slots = asyncio.Semaphore(1)
waveform_slots = asyncio.Semaphore(1)
preview_slots = asyncio.Semaphore(1)
segment_slots = asyncio.Semaphore(2)
PREVIEW_SECONDS = 4
preview_builds = {}
tool_slots = asyncio.Semaphore(1)
TOOL_ROOT = CACHE_DIR / "video_edit_tools"


class Plan(Timeline):
    useClipTools: bool = False
    prompt: str = Field(min_length=1, max_length=1600)
    mediaIds: list[UUID] = Field(default_factory=list, max_length=16)


def owner(user):
    return hashlib.sha256(str(user.id).encode()).hexdigest()


def workspace(user):
    directory = ROOT / owner(user)
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def expire(directory):
    cutoff = time.time() - TTL
    protected = {item["id"] for item in jobs.values() if item["status"] in ACTIVE}
    for path in directory.iterdir():
        if (path.is_file() and re.fullmatch(r"[a-f0-9]{32}\.(?:source|json|jpg|mp4|mp3|srt|(?:proxy|audio)(?:\.part)?\.mp4)", path.name)
                and path.name.split(".")[0] not in protected and path.stat().st_mtime < cutoff):
            path.unlink(missing_ok=True)


def resource(directory, id):
    info = directory / f"{id}.json"
    source = directory / f"{id}.source"
    if not info.is_file() or not source.is_file():
        raise HTTPException(404, "Media not found.")
    now = time.time()
    os.utime(info, (now, now))
    os.utime(source, (now, now))
    return {**json.loads(info.read_text(encoding="utf-8")), "path": source}


def project(directory, timeline):
    assets = {}
    duration = 0
    if timeline.height not in ("original", 480, 720, 1080):
        raise HTTPException(422, "Choose 480p, 720p or 1080p.")
    for clip in timeline.clips:
        try:
            id = UUID(clip.asset).hex
            if id != clip.asset:
                raise ValueError
        except ValueError:
            raise HTTPException(422, "Invalid media identifier.") from None
        if id not in assets:
            assets[id] = resource(directory, id)
        if clip.end - clip.start < .08 or clip.end > assets[id]["duration"] + .01:
            raise HTTPException(422, "A clip has invalid trim points.")
        clip.end = min(clip.end, assets[id]["duration"])
    duration = max(at + clip.end - clip.start for at, clip in positioned(timeline.clips))
    if len(assets) > 16 or duration > (MAX_DURATION if isinstance(timeline, (ExportTimeline, Assistance)) else 1800):
        raise HTTPException(422, "Use at most 16 sources and respect the duration limit for this operation.")
    return assets, duration


def hide_window():
    return {"creationflags": 0x08000000} if os.name == "nt" else {}


def stop_children(pid):
    # Windows venvs run a launcher plus a child interpreter. The latter holds the GPU.
    import psutil
    with suppress(psutil.NoSuchProcess):
        for child in reversed(psutil.Process(pid).children(recursive=True)):
            with suppress(psutil.NoSuchProcess):
                child.kill()


async def run_process(arguments, cwd, job=None, scale=1, offset=0, span=1, *, kill_tree=False):
    # Argument vector only: user content is never evaluated as a shell command.
    with open(os.devnull, "wb") as sink:
        proc = await asyncio.create_subprocess_exec(
            *arguments, cwd=cwd, stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE, stdin=sink, **hide_window(),
        )
        errors = asyncio.create_task(proc.stderr.read())
        try:
            while line := await proc.stdout.readline():
                if job and line.startswith(b"out_time_us="):
                    try:
                        seconds = int(line.split(b"=", 1)[1]) / 1000000
                        job["progress"] = max(job["progress"], min(99, int((offset + seconds / scale * span) * 100)))
                    except ValueError:
                        pass
            if await proc.wait():
                detail = (await errors).decode(errors="replace")[-2000:]
                log.warning("Neve Studio processor error: %s", detail)
                if kill_tree:
                    for message in ("Select a more distinct subject.", "Not enough free GPU memory.", "A CUDA GPU is required."):
                        if message in detail:
                            raise ValueError(message)
                    if "out of memory" in detail.lower():
                        raise ValueError("Not enough free GPU memory.")
                raise ValueError("Could not render this video.")
        finally:
            if proc.returncode is None:
                if kill_tree:
                    await asyncio.to_thread(stop_children, proc.pid)
                with suppress(ProcessLookupError):
                    proc.kill()
                await proc.wait()
            await errors


def read_upload(source, path):
    size = 0
    with path.open("wb") as output:
        while block := source.read(1024 * 1024):
            size += len(block)
            if size > MAX_UPLOAD:
                raise HTTPException(413, "Maximum video size: 32 GiB.")
            output.write(block)


def archive_import(path, user_id, info, mime):
    import mimetypes
    import shutil
    from neveai.config import UPLOAD_DIR
    from neveai.models.files import FileForm, Files

    archive_id = str(uuid4())
    ext = Path(info["name"]).suffix.lower()
    ext = ext if re.fullmatch(r"\.[a-z0-9]{1,8}", ext) else ".video"
    archive = Path(UPLOAD_DIR) / (archive_id + ext)
    try:
        try:
            os.link(path, archive)
        except OSError:
            shutil.copyfile(path, archive)
        meta = {"name": info["name"], "size": path.stat().st_size, "content_type": mime if mime and mime.startswith("video/") else mimetypes.guess_type(info["name"])[0] or "video/mp4"}
        if not Files.insert_new_file(user_id, FileForm(id=archive_id, filename=info["name"], path=archive.as_posix(), meta=meta)):
            raise ValueError("Could not register the imported video.")
        return archive_id
    except BaseException:
        archive.unlink(missing_ok=True)
        raise


@router.post("/media")
async def upload(request: Request, file: UploadFile | None = None, user=Depends(get_verified_user)):
    directory = workspace(user)
    await asyncio.to_thread(expire, directory)
    id = uuid4().hex
    path = directory / f"{id}.source"
    proxy = directory / f"{id}.proxy.mp4"
    thumbnail = directory / f"{id}.jpg"
    try:
        async with uploads:
            if not file and request.headers.get("content-type") != "application/octet-stream":
                raise HTTPException(422, "Select a video file.")
            length = file.size if file else int(request.headers.get("content-length") or 0)
            if length and length > MAX_UPLOAD:
                raise HTTPException(413, "Maximum video size: 32 GiB.")
            if length and length + 128 * 1024**2 > shutil.disk_usage(directory).free:
                raise HTTPException(507, "Not enough free disk space.")
            if file:
                await asyncio.to_thread(read_upload, file.file, path)
            else:
                size = 0
                buffer = bytearray()
                with path.open("xb") as target:
                    async for chunk in request.stream():
                        size += len(chunk)
                        if size > MAX_UPLOAD:
                            raise HTTPException(413, "Maximum video size: 32 GiB.")
                        buffer.extend(chunk)
                        if len(buffer)>=1024**2:
                            await asyncio.to_thread(target.write, buffer)
                            buffer.clear()
                    if buffer:
                        await asyncio.to_thread(target.write,buffer)
            info = await asyncio.to_thread(probe, path, thumbnail)
        if await request.is_disconnected():
            raise HTTPException(499, "Cancelled.")
        name = file.filename if file else unquote(request.headers.get("x-studio-filename", ""))
        info.update(id=id, name=(name or "Video").replace("\\", "/").rsplit("/", 1)[-1][:160])
        (directory / f"{id}.json").write_text(json.dumps(info), encoding="utf-8")
        info["fileId"] = await asyncio.to_thread(archive_import, path, user.id, info, file.content_type if file else None)
        return info
    except BaseException as error:
        (directory / f"{id}.json").unlink(missing_ok=True)
        path.unlink(missing_ok=True)
        proxy.unlink(missing_ok=True)
        thumbnail.unlink(missing_ok=True)
        if isinstance(error,OSError) and error.errno == 28:
            raise HTTPException(507, "Not enough free disk space.") from None
        if isinstance(error, (HTTPException, asyncio.CancelledError)):
            raise
        raise HTTPException(422, str(error) if isinstance(error, ValueError) else "Could not open this video.") from None


class ClipTool(BaseModel):
    requestId: UUID | None = None
    operation: Literal["fps60", "vocals", "instrumental", "erase"]
    anchor: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    selection: str | None = Field(default=None, max_length=800000)
    point: tuple[float, float] | None = None
    points: list[tuple[float, float, Literal[0, 1]]] = Field(default_factory=list, max_length=16)
    box: tuple[float, float, float, float] | None = None
    start: float = Field(ge=0, allow_inf_nan=False)
    end: float = Field(gt=0, allow_inf_nan=False)


@router.get("/clip-tools")
def clip_tools(user=Depends(get_verified_user)):
    return available(TOOL_ROOT)


class FrameSelection(BaseModel):
    operation: Literal["erase"]
    start: float = Field(ge=0, allow_inf_nan=False)
    points: list[tuple[float, float, Literal[0, 1]]] = Field(default_factory=list, max_length=64)


@router.post("/media/{media_id}/selection")
def select_region(media_id: UUID, params: FrameSelection, user=Depends(get_verified_user)):
    from types import SimpleNamespace
    from neveai.routers.image_mode_selection import click_selector
    src = resource(workspace(user), media_id.hex)
    if (params.start >= src["duration"] or any(not (0 <= x <= 1 and 0 <= y <= 1) for x,y,_ in params.points)
            or params.points and not any(label for _,_,label in params.points)):
        raise HTTPException(422, "Select a distinct region in the frame.")
    fps, width, height = shot_geometry(src)
    try:
        frame = selection_frame(src["path"], src["videoIndex"], params.start, fps, width, height)
    except (subprocess.SubprocessError, OSError) as exc:
        raise HTTPException(422, "Could not decode the selected frame.") from exc
    if not frame:
        raise HTTPException(422, "Could not decode the selected frame.")
    if not params.points:
        return {"frame": "data:image/png;base64," + base64.b64encode(frame).decode("ascii"), "width": width, "height": height}
    pos, neg = [], []
    for x,y,label in params.points:
        (pos if label else neg).append(SimpleNamespace(x=x,y=y))
    from PIL import Image
    from io import BytesIO
    mask = click_selector.select(frame, pos, neg, user.id)
    with Image.open(BytesIO(base64.b64decode(mask.split(",",1)[1]))) as im:
        if im.getextrema() != (0,255):
            raise HTTPException(422, "Select a distinct region in the frame.")
    return {"mask": mask}


@asynccontextmanager
async def clip_device(operation):
    if operation in ("vocals", "instrumental"):
        yield
        return
    from neveai.utils.middleware import _MEDIA_GENERATION_LOCK
    from neveai.utils.model_availability import media_is_busy
    from neveai.utils.voice_priority import primary_gpu_work
    if media_is_busy() or _MEDIA_GENERATION_LOCK.locked():
        raise HTTPException(409, "Another media generation is using the GPU.")
    async with _MEDIA_GENERATION_LOCK, primary_gpu_work():
        yield


@router.post("/media/{media_id}/process")
async def derived_media(media_id: UUID, params: ClipTool, request: Request, user=Depends(get_verified_user)):
    return await tracked_edit(params.requestId,request,user,lambda: process_media(media_id,params,request,user),derived=True)


async def tracked_edit(operation_id, request, user, work, derived=False):
    if operation_id is None:
        return await work()
    key=(owner(user),operation_id)
    if key in edit_operations:
        raise HTTPException(409,"Operation already finished or cancelled.")
    state={"cancel":False,"done":asyncio.Event(),"asset":None}
    edit_operations[key]=request.state.studio_operation=state
    try:
        result=await work()
        if derived: state["asset"]=result["id"]
        return result
    finally:
        state["done"].set()
        asyncio.get_running_loop().call_later(90,edit_operations.pop,key,None)


async def edit_cancelled(request):
    return getattr(request.state,"studio_operation",{}).get("cancel") or await request.is_disconnected()


@router.delete("/operations/{operation_id}")
async def cancel_edit(operation_id: UUID,user=Depends(get_verified_user)):
    key=(owner(user),operation_id)
    state=edit_operations.get(key)
    if state is None:
        # Cancellation can race the initial POST.
        state={"cancel":True,"done":asyncio.Event(),"asset":None}
        state["done"].set()
        edit_operations[key]=state
        asyncio.get_running_loop().call_later(90,edit_operations.pop,key,None)
    state["cancel"]=True
    await state["done"].wait()
    if state["asset"]:
        directory=workspace(user)
        for ext in ("source","json","jpg"):
            (directory/f"{state['asset']}.{ext}").unlink(missing_ok=True)
    return {"cancelled":True}


async def process_media(media_id,params,request,user):
    directory = workspace(user)
    source = resource(directory, media_id.hex)
    if tool_slots.locked():
        raise HTTPException(409, "Another clip is being processed.")
    async with tool_slots, clip_device(params.operation):
        id = uuid4().hex
        with TemporaryDirectory(prefix="clip-", dir=directory) as temp:
            work = Path(temp)
            output = work / "output.mp4"
            async def run_tool(arguments, cwd):
                await run_process(arguments, cwd, kill_tree=True)
            task = asyncio.create_task(process_tool(params.operation, source, params.start, params.end,
                                                    TOOL_ROOT, work, output, run_tool, point=params.point, points=params.points,
                                                    box=params.box, selection=params.selection, anchor=params.anchor))
            try:
                # A long visual edit has multiple inference windows. Disconnection still cancels the job.
                timeout = None if params.operation == "erase" else 1800
                if params.operation in ("vocals", "instrumental"):
                    timeout = max(1800, (params.end-params.start)*12)
                async with asyncio.timeout(timeout):
                    while not task.done():
                        if await edit_cancelled(request):
                            raise HTTPException(499, "Cancelled.")
                        await asyncio.wait({task}, timeout=.4)
                    await task
                info = await asyncio.to_thread(probe, output, work / "poster.jpg")
                if await edit_cancelled(request):
                    raise HTTPException(499,"Cancelled.")
                info.update(id=id, name=f"{Path(source['name']).stem[:120]} - {params.operation}.mp4",
                            interpolated=params.operation == "fps60")
                (work / "info.json").write_text(json.dumps(info), encoding="utf-8")
                output.replace(directory / f"{id}.source")
                (work / "poster.jpg").replace(directory / f"{id}.jpg")
                (work / "info.json").replace(directory / f"{id}.json")
                return info
            except TimeoutError:
                raise HTTPException(408, "Clip processing timed out.") from None
            except ValueError as exc:
                raise HTTPException(422, str(exc)) from None
            finally:
                if not task.done():
                    task.cancel()
                    with suppress(asyncio.CancelledError):
                        await task


preview_reads = {}
discard_after_download = set()


class PreviewResponse(FileResponse):
    async def __call__(self, scope, receive, send):
        task = asyncio.create_task(super().__call__(scope, receive, send))
        reads = preview_reads.setdefault(self.path, set())
        reads.add(task)
        try:
            await task
        finally:
            reads.discard(task)
            if not reads:
                preview_reads.pop(self.path, None)
                if self.path in discard_after_download:
                    discard_after_download.discard(self.path)
                    self.path.unlink(missing_ok=True)


@router.get("/media/{media_id}")
async def preview(media_id: UUID, request: Request, audio: bool = False, user=Depends(get_verified_user)):
    directory = workspace(user)
    info = resource(directory, media_id.hex)
    source = info["path"]
    if audio and not info["audio"]:
        raise HTTPException(404, "No audio track.")
    path = directory / f"{media_id.hex}.audio.mp4" if audio else source if info["browserReady"] else directory / f"{media_id.hex}.proxy.mp4"
    if path != source and not path.is_file():
        async with preview_slots:
            if not path.is_file():
                if not source.is_file() or await request.is_disconnected():
                    raise HTTPException(404, "Media not available.")
                part = path.with_suffix(".part.mp4")
                try:
                    streams = ["-vn", "-map", "0:a:0"] if audio else [
                        "-map", f"0:{info['videoIndex']}", "-map", "0:a:0?", "-vf",
                        "scale=1280:720:force_original_aspect_ratio=decrease:force_divisible_by=2",
                        "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p", "-threads", "3"]
                    proc = asyncio.create_task(run_process([ffmpeg_binary(), "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
                        "-protocol_whitelist", "file", "-format_whitelist", FORMATS, "-i", str(source),
                        *streams, "-c:a", "aac", "-movflags", "+faststart", str(part)], directory))
                    preview_builds[path] = proc
                    try:
                        while not proc.done():
                            await asyncio.wait([proc], timeout=.4)
                            if not proc.done() and await request.is_disconnected():
                                raise HTTPException(499, "Cancelled.")
                        await proc
                    finally:
                        preview_builds.pop(path,None)
                        proc.cancel()
                        await asyncio.gather(proc,return_exceptions=True)
                    if not source.exists():
                        raise HTTPException(404, "Media not found.")
                    part.replace(path)
                finally:
                    part.unlink(missing_ok=True)
    if path != info["path"] and path.exists():
        os.utime(path, None)
    return PreviewResponse(path, media_type="audio/mp4" if audio else "video/mp4")


@router.get("/media/{media_id}/preview.m3u8")
def preview_playlist(media_id: UUID, audio: bool = False, user=Depends(get_verified_user)):
    info = resource(workspace(user), media_id.hex)
    duration = info["duration"]
    rows = ["#EXTM3U", "#EXT-X-VERSION:3", "#EXT-X-PLAYLIST-TYPE:VOD",
            "#EXT-X-INDEPENDENT-SEGMENTS", f"#EXT-X-TARGETDURATION:{PREVIEW_SECONDS}", "#EXT-X-MEDIA-SEQUENCE:0"]
    for i in range(math.ceil(duration / PREVIEW_SECONDS)):
        rows.extend([f"#EXTINF:{min(PREVIEW_SECONDS, duration-i*PREVIEW_SECONDS):.6f},",
                     f"segments/{i}.ts" + ("?audio=true" if audio else "")])
    return Response("\n".join([*rows, "#EXT-X-ENDLIST", ""]), media_type="application/vnd.apple.mpegurl")


@router.get("/media/{media_id}/segments/{index}.ts")
async def preview_segment(media_id: UUID, index: int, request: Request, audio: bool = False, user=Depends(get_verified_user)):
    directory = workspace(user)
    info = resource(directory, media_id.hex)
    start = index * PREVIEW_SECONDS
    if not 0 <= start < info["duration"] or audio and not info["audio"]:
        raise HTTPException(404, "No such segment.")
    streams = ["-vn", "-map", "0:a:0"] if audio else [
        "-map", f"0:{info['videoIndex']}", "-map", "0:a:0?", "-vf",
        "scale=w='min(iw,1280)':h='min(ih,720)':force_original_aspect_ratio=decrease:force_divisible_by=2",
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23", "-maxrate", "5M", "-bufsize", "5M",
        "-bf", "0", "-pix_fmt", "yuv420p", "-threads", "2"]
    async with segment_slots:
        if await request.is_disconnected():
            raise HTTPException(499, "Cancelled.")
        with TemporaryDirectory(dir=directory) as temp:
            path = Path(temp) / "preview.ts"
            cmd = [ffmpeg_binary(), "-nostdin", "-v", "error", "-protocol_whitelist", "file", "-format_whitelist", FORMATS,
                   "-threads", "2", "-ss", str(start), "-i", str(info["path"]), "-t", str(min(PREVIEW_SECONDS, info["duration"]-start)),
                   *streams, "-c:a", "aac", "-ar", "48000", "-ac", "2", "-b:a", "128k", "-output_ts_offset", str(start),
                   "-muxdelay", "0", "-f", "mpegts", str(path)]
            await run_process(cmd, directory)
            return Response(await asyncio.to_thread(path.read_bytes), media_type="video/mp2t",
                            headers={"Cache-Control": "private, max-age=3600"})


@router.get("/media/{media_id}/speaker-sample")
async def speaker_sample(media_id: UUID, start: float, end: float, user=Depends(get_verified_user)):
    directory=workspace(user)
    info=resource(directory,media_id.hex)
    if not (0 <= start < end <= info["duration"]+.05 and end-start <= 3.001 and info["audio"]):
        raise HTTPException(422,"Invalid audio excerpt.")
    async with segment_slots:
        with TemporaryDirectory(dir=directory) as temp:
            out=Path(temp)/"sample.wav"
            await run_process([ffmpeg_binary(),"-nostdin","-v","error","-protocol_whitelist","file",
                               "-format_whitelist",FORMATS,"-ss",str(start),"-i",str(info["path"]),
                               "-t",str(min(3,end-start)),"-map","0:a:0","-vn","-ac","1","-ar","24000",
                               "-c:a","pcm_s16le",str(out)],directory)
            return Response(out.read_bytes(),media_type="audio/wav",headers={"Cache-Control":"private, max-age=3600"})


@router.get("/media/{media_id}/thumbnail")
def poster(media_id: UUID, user=Depends(get_verified_user)):
    directory = workspace(user)
    resource(directory, media_id.hex)
    path = directory / f"{media_id.hex}.jpg"
    if not path.is_file():
        raise HTTPException(404, "Media not found.")
    os.utime(path, None)
    return FileResponse(path, media_type="image/jpeg")


@router.get("/media/{media_id}/waveform")
async def waveform(media_id: UUID, request: Request, user=Depends(get_verified_user)):
    info = resource(workspace(user), media_id.hex)
    if not info["audio"]:
        return {"samples": []}
    async with waveform_slots:
        if await request.is_disconnected():
            return {"samples":[]}
        stopped = Event()
        scan = asyncio.create_task(asyncio.to_thread(preview_waveform, info["path"], info["duration"], stopped))
        try:
            while not scan.done():
                await asyncio.wait([scan],timeout=.25)
                if not scan.done() and await request.is_disconnected():
                    stopped.set()
            samples = scan.result()
        except Exception:
            log.info("Neve Studio waveform unavailable for %s", media_id.hex, exc_info=True)
            samples = []
        finally:
            stopped.set()
    return {"samples": samples}


async def plan_edit(request, user, progress):
    async with analysis_slots:
        assets, duration = await asyncio.to_thread(project, workspace(user), request)
        for value in request.mediaIds:
            if value.hex not in assets:
                assets[value.hex] = await asyncio.to_thread(resource, workspace(user), value.hex)
        if len(assets) > 16:
            raise HTTPException(422, "Use at most 16 sources and 30 minutes on the timeline.")
        def report(phase, step=None, total=None):
            progress({"phase": phase, "step": step, "total": total, "model": MODEL_NAME})
        try:
            async with director_model(report) as (info, complete):
                edit, summary, audio = await asyncio.wait_for(
                    direct_edit(request, request.prompt, assets, complete, WHISPER_MODEL_DIR, report, info["n_ctx"]),
                    min(3600, max(480, duration * 3)),
                )
            await asyncio.to_thread(project, workspace(user), edit)
            return {**edit.model_dump(exclude={"prompt", "mediaIds"}), "summary": summary, "model": info["filename"],
                    "waves": {asset: facts["wave"] for asset, facts in audio.items()}}
        except RequestedClipTool as tool:
            if tool.args[0] not in available(TOOL_ROOT):
                raise HTTPException(409, "This clip tool is not installed.") from None
            return {"clipTool": tool.args[0]}
        except TimeoutError:
            raise HTTPException(504, "The local edit timed out. The timeline was kept unchanged.") from None
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from None
        except HTTPException:
            raise
        except Exception:
            log.exception("Local video director failed")
            raise HTTPException(422, "The local vision or transcription model could not finish the edit.") from None


class TranscriptSpan(BaseModel):
    asset: str
    start: float = Field(ge=0, le=MAX_DURATION)
    end: float = Field(gt=0, le=MAX_DURATION+1)


class Assistance(Timeline):
    speakerCount: int | None = Field(default=None,ge=1,le=32)
    requestId: UUID | None = None
    transcriptCoverage: list[TranscriptSpan] = Field(default_factory=list,max_length=4000)
    operation: Literal["captions", "words", "speech", "color", "speakers"]
    index: int = Field(ge=0, lt=MAX_CLIPS)


@router.post("/assist")
async def assist_clip(params: Assistance, request: Request, user=Depends(get_verified_user)):
    return await tracked_edit(params.requestId,request,user,lambda: analyze_clip(params,request,user))


async def analyze_clip(params,request,user):
    from neveai.utils.video_edit_selection import ripple_ranges, union
    directory = workspace(user)
    media, total = project(directory, params)
    if params.index >= len(params.clips):
        raise HTTPException(422, "Select a clip.")
    at, clip = list(positioned(params.clips))[params.index]
    if clip.end-clip.start > MAX_DURATION:
        raise HTTPException(422, "Select a clip of up to 5 hours.")
    source = media[clip.asset]
    if params.operation != "color" and not source["audio"]:
        raise HTTPException(422, "This clip has no audio.")
    if analysis_slots.locked():
        raise HTTPException(409, "Another clip is being processed.")
    async with analysis_slots:
        with TemporaryDirectory(dir=directory) as temp:
            result = Path(temp).resolve() / "result.json"
            args = [sys.executable, "-m", "neveai.utils.video_edit_assist", str(source["path"].resolve()),
                    str(clip.start), str(clip.end), params.operation, str(Path(WHISPER_MODEL_DIR).resolve()), str(result),
                    str((Path(CACHE_DIR) / "video_edit_speakers").resolve())]
            if params.operation in ("captions","speakers","words"):
                from neveai.utils.video_edit_assist import transcription_gaps
                existing = [{"existingIndex":i,"text":c.text,"start":max(clip.start,c.start),"end":min(clip.end,c.end)}
                            for i,c in enumerate(params.captions) if c.asset==clip.asset and c.start<clip.end and c.end>clip.start]
                covered = [(s.start,s.end) for s in params.transcriptCoverage if s.asset==clip.asset]
                gaps = transcription_gaps(clip.start,clip.end,covered+[(c["start"],c["end"]) for c in existing])
                if not gaps and (params.operation!="speakers" or not existing):
                    return {"cues":[]}
                plan = result.with_name("transcription.json")
                plan.write_text(json.dumps({"existing":existing,"gaps":gaps,"speakerCount":params.speakerCount}),encoding="utf8")
                args.append(str(plan))
            task = asyncio.create_task(run_process(args, Path(__file__).resolve().parents[2], kill_tree=True))
            try:
                async with asyncio.timeout(max(1800,(clip.end-clip.start)*6)):
                    while not task.done():
                        if await edit_cancelled(request):
                            raise HTTPException(499, "Cancelled.")
                        await asyncio.wait({task}, timeout=.4)
                    await task
                data = json.loads(result.read_text(encoding="utf8"))
                if await edit_cancelled(request):
                    raise HTTPException(499,"Cancelled.")
                if params.operation == "color":
                    return data
                if not data["speech"] and params.operation=="speech":
                    raise HTTPException(422, "No speech detected. The timeline was not changed.")
                if params.operation == "speech":
                    length = clip.end-clip.start
                    kept = union([(0, at), (at+length, total)] + [(at+x, at+y) for x,y in data["speech"]])
                    edit, _ = ripple_ranges(params, kept, True)
                    return {"clips": edit.clips}
                if sum("existingIndex" not in cue for cue in data["cues"]) + len(params.captions) > MAX_CAPTIONS:
                    raise HTTPException(422, "Too many captions. Select a shorter clip.")
                return {"cues": data["cues"], **({"samples":data["samples"]} if "samples" in data else {})}
            except TimeoutError:
                raise HTTPException(408, "Analysis timed out.") from None
            except ValueError as exc:
                raise HTTPException(422, str(exc)) from None
            finally:
                if not task.done():
                    task.cancel()
                    with suppress(asyncio.CancelledError):
                        await task


@router.post("/plan")
async def plan(request: Plan, user=Depends(get_verified_user)):
    return await plan_edit(request, user, lambda _: None)


@router.post("/plan/progress")
async def plan_progress(request: Plan, user=Depends(get_verified_user)):
    async def events():
        queue = asyncio.Queue()
        async def work():
            try:
                result = await plan_edit(request, user, lambda event: queue.put_nowait({"progress": event}))
                queue.put_nowait({"result": result})
            except HTTPException as error:
                queue.put_nowait({"error": error.detail})
            except Exception:
                log.exception("Video planning failed before analysis")
                queue.put_nowait({"error": "Neve Studio request failed."})
        task = asyncio.create_task(work())
        try:
            while True:
                item = await queue.get()
                yield json.dumps(item, ensure_ascii=False) + "\n"
                if "progress" not in item:
                    break
        finally:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
    return StreamingResponse(events(), media_type="application/x-ndjson", headers={"Cache-Control": "no-store"})


def render_size(info, height, aspect="source"):
    if aspect == "portrait":
        return height, round(height * 16 / 9 / 2) * 2
    if aspect == "landscape":
        return round(height * 16 / 9 / 2) * 2, height
    ratio = info["width"] / info["height"]
    if ratio >= 1:
        return max(2, round(height * min(ratio, 16 / 9) / 2) * 2), height
    return (height if ratio >= 9 / 16 else max(2, round(height * ratio * 16 / 9 / 2) * 2),
            round(height * 16 / 9 / 2) * 2)


async def render(job, directory, timeline, assets, total):
    import tempfile

    kind = job.get("format", "mp4")
    destination = directory / f"{job['id']}.{kind}"
    try:
        async with workers:
            job["status"] = "exporting"
            with tempfile.TemporaryDirectory(prefix="render-", dir=directory) as working:
                work = Path(working)
                if kind == "mp3":
                    # Video-only edits must not split an otherwise continuous audio encode.
                    audible = [c.model_copy(update={"at": at}) for at,c in positioned(timeline.clips)
                               if c.gain and not c.noAudio and assets[c.asset]["audio"]]
                    spans = list(layer_slices(audible, 48000))
                    end = spans[-1][1] if spans else 0
                    if total-end > 1/48000:
                        spans.append((end,total,None,[]))
                    if len(spans)==1:
                        at,end,_,active = spans[0]
                        cmd,filters,_,audio = render_layer_command(at,end-at,None,active,assets,0,0,0,audio_only=True)
                        if timeline.normalize:
                            filters += f";{audio}loudnorm=I=-16:TP=-1.5:LRA=9,aresample=48000[out]"
                            audio = "[out]"
                        await run_process(cmd+["-filter_complex",filters,"-map",audio,"-vn","-t",f"{total:.6f}",
                                               "-c:a","libmp3lame","-b:a",f"{timeline.bitrate}k",str(destination)],work,job,total,0,.99)
                        job.update(status="done", progress=100)
                        return
                    parts = []
                    for i, (at, end, _, active) in enumerate(spans):
                        length = end - at
                        cmd, filters, _, audio = render_layer_command(at, length, None, active, assets, 0, 0, 0, audio_only=True)
                        part = f"audio{i:03}.wav"
                        await run_process(cmd + ["-filter_complex", filters, "-map", audio, "-c:a", "pcm_s16le", "-t", f"{length:.6f}", part],
                                          work, job, length, .8 * at / total, .8 * length / total)
                        parts.append(f"file '{part}'\n")
                    (work / "parts.txt").write_text("".join(parts), encoding="ascii")
                    cmd = [ffmpeg_binary(), "-nostdin", "-hide_banner", "-loglevel", "error", "-y", "-progress", "pipe:1",
                           "-f", "concat", "-safe", "1", "-i", "parts.txt", "-vn"]
                    if timeline.normalize:
                        cmd += ["-af", "loudnorm=I=-16:TP=-1.5:LRA=9,aresample=48000"]
                    await run_process(cmd + ["-c:a", "libmp3lame", "-b:a", f"{timeline.bitrate}k", str(destination)],
                                      work, job, total, .8, .2)
                    job.update(status="done", progress=100)
                    return
                first = assets[next((c.asset for c in timeline.clips if not c.audioOnly), timeline.clips[0].asset)]
                original = timeline.height == "original"
                if original:
                    _, base = min(((at, c) for at, c in positioned(timeline.clips) if not c.audioOnly),
                                  key=lambda item: (item[0], item[1].lane))
                    first = assets[base.asset]
                    w, h = first["width"], first["height"]
                    # The composition filters use 4:2:0; trim odd-sized sources back at the final encode.
                    width, height = w + w % 2, h + h % 2
                else:
                    width, height = render_size(first, timeline.height, timeline.aspect)
                fill = timeline.aspect != "source"
                fps = max(15, min(60, round(first["fps"])))
                if any(assets[c.asset].get("interpolated") for c in timeline.clips if not c.audioOnly):
                    fps = 60
                cues = list(projected_captions(timeline.clips, timeline.captions, styled=True))
                encode_video = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "19", "-threads", "4", "-pix_fmt", "yuv420p"]
                budget = .72 if cues or timeline.normalize or timeline.title else .97
                offset = 0
                parts = list(layer_slices(timeline.clips, fps)) if layered(timeline.clips) else timeline.clips
                for index, clip in enumerate(parts):
                    part = f"part{index:03}.mkv"
                    if isinstance(clip, tuple):
                        at, end, visible, active = clip
                        length = end - at
                        command, filters, video, audio = render_layer_command(at, length, visible, active, assets, width, height, fps, fill)
                    else:
                        length = clip.end - clip.start
                        command, filters, video, audio = render_command(
                            [clip.model_copy(update={"start": 0, "end": length})], assets, width, height, fps, False, False, fill, clip.start)
                        command[command.index("-i"):command.index("-i")] = ["-ss", f"{clip.start:.6f}"]
                    await run_process(command + ["-filter_complex", filters, "-map", video, "-map", audio,
                                                 *encode_video, "-c:a", "pcm_s16le", "-t", f"{length:.6f}", part],
                                      work, job, length, offset * budget / total, length * budget / total)
                    offset += length
                (work / "parts.txt").write_text("".join(f"file 'part{i:03}.mkv'\n" for i in range(len(parts))), encoding="ascii")
                command = [ffmpeg_binary(), "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
                           "-progress", "pipe:1", "-f", "concat", "-safe", "1", "-i", "parts.txt"]
                overlay = []
                if timeline.title:
                    write_intro(work / "intro.ass", timeline.title, total, height > width)
                    if (work / "intro.ass").is_file():
                        overlay.append("ass=intro.ass")
                if cues:
                    from neveai.utils.video_edit_captions import write_animated
                    write_animated(work / "captions.ass", cues, timeline.captionStyle, width, height)
                    overlay.append("ass=captions.ass")
                if original and (width != w or height != h):
                    overlay.append(f"format=yuv444p,crop={w}:{h}:0:0:exact=1")
                    encode_video[-1] = "yuv444p"
                if overlay:
                    command += ["-vf", ",".join(overlay)]
                if timeline.normalize:
                    command += ["-af", "loudnorm=I=-16:TP=-1.5:LRA=9,aresample=48000"]
                # Keep audio in PCM until this final pass so effect boundaries do not add AAC priming gaps.
                command += encode_video if overlay else ["-c:v", "copy"]
                command += ["-c:a", "aac", "-b:a", "160k"] if any(not c.noAudio and assets[c.asset]["audio"] for c in timeline.clips) else ["-an"]
                await run_process(command + ["-movflags", "+faststart", str(destination)], work, job, total, budget, 1-budget)
                job.update(status="done", progress=100, captions=bool(cues))
    except asyncio.CancelledError:
        destination.unlink(missing_ok=True)
        job["status"] = "cancelled"
        raise
    except Exception:
        destination.unlink(missing_ok=True)
        log.exception("Neve Edit export failed")
        job.update(status="failed", error="Could not render this video.")


def public(job):
    return {key: val for key, val in job.items() if key not in {"task", "owner", "created"}}


class ExportTimeline(Timeline):
    height: Literal["original", 480, 720, 1080] = 1080
    format: Literal["mp4", "mp3"] = "mp4"
    bitrate: Literal[128, 192, 256, 320] = 192


@router.post("/exports", status_code=202)
async def export(timeline: ExportTimeline, user=Depends(get_verified_user)):
    directory = workspace(user)
    assets, duration = await asyncio.to_thread(project, directory, timeline)
    kind = getattr(timeline, "format", "mp4")
    if kind == "mp4" and not any(not c.audioOnly for c in timeline.clips):
        raise HTTPException(422, "No video track to export.")
    if kind == "mp3" and not any(not c.noAudio and assets[c.asset]["audio"] for c in timeline.clips):
        raise HTTPException(422, "No audio track to export.")
    for key, item in list(jobs.items()):
        if item["status"] not in ACTIVE and item["created"] < time.time() - TTL:
            jobs.pop(key, None)
    if any(j["owner"] == owner(user) and j["status"] in ACTIVE for j in jobs.values()):
        raise HTTPException(409, "A video export is already running.")
    id = uuid4().hex
    job = {"id": id, "owner": owner(user), "created": time.time(), "status": "queued", "progress": 0, "format": kind}
    jobs[id] = job
    job["task"] = asyncio.create_task(render(job, directory, timeline, assets, duration))
    return public(job)


def get_job(job_id, user):
    job = jobs.get(job_id.hex)
    if not job or job["owner"] != owner(user):
        raise HTTPException(404, "Export not found.")
    return job


@router.get("/exports/{job_id}")
async def export_status(job_id: UUID, user=Depends(get_verified_user)):
    return public(get_job(job_id, user))


@router.delete("/exports/{job_id}")
async def cancel(job_id: UUID, user=Depends(get_verified_user)):
    job = get_job(job_id, user)
    if job["status"] in ACTIVE:
        job["status"] = "cancelled"
        job["task"].cancel()
        await asyncio.gather(job["task"], return_exceptions=True)
    return public(job)


class Discard(BaseModel):
    media: list[UUID] = Field(max_length=2048)
    exports: list[UUID] = Field(max_length=2048)


@router.post("/discard")
async def discard_session(params: Discard, user=Depends(get_verified_user)):
    directory = workspace(user)
    completed = []
    for id in params.exports:
        if id.hex in jobs and jobs[id.hex]["owner"] == owner(user):
            await cancel(id, user)
            jobs.pop(id.hex, None)
        for ext in ("mp4", "mp3", "srt"):
            path = directory / f"{id.hex}.{ext}"
            if preview_reads.get(path):
                discard_after_download.add(path)
            else:
                completed.append(path)
    pending = [directory / f"{id.hex}.{ext}" for id in params.media for ext in ("source","proxy.mp4","audio.mp4","jpg","json")]
    readers = {task for path in pending for task in preview_reads.get(path, ())}
    readers.update(preview_builds[path] for path in pending if path in preview_builds)
    for task in readers:
        task.cancel()
    if readers:
        await asyncio.gather(*readers, return_exceptions=True)
    pending.extend(completed)
    # Windows releases open media handles just after the monitor is unmounted.
    for attempt in range(6):
        locked = []
        for path in pending:
            try:
                path.unlink(missing_ok=True)
            except PermissionError:
                locked.append(path)
        if not locked:
            break
        if attempt == 5:
            raise HTTPException(409, "Media is still in use.")
        pending = locked
        await asyncio.sleep(.1*(attempt+1))
    return {"discarded": True}


@router.get("/exports/{job_id}/{kind}")
def download(job_id: UUID, kind: str, user=Depends(get_verified_user)):
    if kind not in ("mp4", "mp3"):
        raise HTTPException(404, "Export not found.")
    path = workspace(user) / f"{job_id.hex}.{kind}"
    job = get_job(job_id, user)
    if job["status"] != "done" or job.get("format", "mp4") != kind or not path.is_file():
        raise HTTPException(404, "Export not found.")
    return PreviewResponse(path, filename=f"Neve-Studio.{kind}",
                        media_type="video/mp4" if kind == "mp4" else "audio/mpeg")
