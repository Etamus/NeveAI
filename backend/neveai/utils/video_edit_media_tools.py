"""Apply an offline processor to a trim, never to the original source file."""
import os
import base64
import json
import math
from io import BytesIO
import asyncio
import shutil
import sys
import tempfile
import subprocess
from functools import lru_cache
from pathlib import Path

from neveai.utils.video_edit import FORMATS, ffmpeg_binary
from neveai.utils.video_edit_tool_assets import MDX, REMASTER, RIFE_FILES, windows_rife


def available(root):
    tools = []
    if (root / REMASTER).is_file():
        tools.append("remaster")
    if (root / MDX).is_file():
        tools.extend(("vocals", "instrumental"))
    if windows_rife() and all((root / name).is_file() for name in RIFE_FILES):
        tools.append("fps60")
    sam = (root/"sam2/model.safetensors").is_file()
    if sam and (root / "mask-tools.ready").is_file() and (root/"propainter/weights/ProPainter.pth").is_file():
        tools.append("erase")
    return tools


def shot_geometry(info):
    w, h = info["width"], info["height"]
    scale = min(1, 864/max(w,h), 480/min(w,h))
    return (max(1, min(30, round(info["fps"]))),
            *(max(16, round(v*scale/16)*16) for v in (w,h)))


@lru_cache(maxsize=4)
def selection_frame(path, index, start, fps, width, height):
    # Sample the native reference frame, independent of the effect's internal cadence.
    def extract(at, extra=()):
        return subprocess.run([ffmpeg_binary(), "-nostdin", "-v", "error", "-protocol_whitelist", "file",
        "-format_whitelist", FORMATS, "-ss", str(at), "-i", str(path), "-map", f"0:{index}",
        "-vf", f"scale={width}:{height}" + "".join(extra), "-frames:v", "1", "-threads", "2",
        "-c:v", "png", "-f", "image2pipe", "pipe:1"], capture_output=True, check=True,
        timeout=20, creationflags=0x08000000 if os.name == "nt" else 0).stdout
    frame = extract(start)
    return frame or extract(max(0, start-1), (",reverse",))


def save_selection(encoded, work, size):
    from PIL import Image
    try:
        with Image.open(BytesIO(base64.b64decode(encoded, validate=True))) as im:
            if im.format != "PNG" or im.size != size or im.mode not in ("1", "L"):
                raise ValueError
            mask = im.convert("L").point(lambda x: 255 if x >= 128 else 0)
            if mask.getextrema() != (0, 255):
                raise ValueError
            mask.save(work/"selection.png")
    except (OSError, ValueError, Image.DecompressionBombError):
        raise ValueError("Select a distinct region in the frame.") from None


async def process_tool(action, info, start, end, root, work, dest, run, point=None,
                       points=None, box=None, selection=None, anchor=None):
    if action not in available(root):
        raise ValueError("This clip tool is not installed.")
    duration = end - start
    masked = action == "erase"
    stem = action in ("vocals", "instrumental")
    limit, message = (3600, "Select a clip of up to 1 hour.") if stem else (
        (1800, "Select a clip of up to 30 minutes.") if masked else (300, "Select a clip of up to 5 minutes."))
    if not 0 <= start < end <= info["duration"] + .001 or not .08 <= duration <= limit:
        raise ValueError(message)
    # The stem worker memory-maps stereo float32 input and writes a second stem of equal size.
    if shutil.disk_usage(work).free < 1024**3 + (math.ceil(duration)*44100*2*4*2 if stem else 0):
        raise ValueError("Not enough free disk space.")
    ff = [ffmpeg_binary(), "-nostdin", "-v", "error", "-y"]
    def source(at):
        return ["-protocol_whitelist", "file", "-format_whitelist", FORMATS, "-ss", str(at), "-i", str(info["path"])]
    encode = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "17", "-threads", "4", "-pix_fmt", "yuv420p"]
    finish = ["-c:a", "aac", "-b:a", "256k", "-movflags", "+faststart", "-f", "mp4", str(dest)]
    if action == "remaster":
        import av
        from neveai.utils.video_edit import INPUT_OPTIONS
        with av.open(str(info["path"]), options=INPUT_OPTIONS) as media:
            if media.streams[info["videoIndex"]].codec_context.color_trc in (16, 18):
                raise ValueError("Video enhancement supports SDR clips only.")
        await run([sys.executable, str(Path(__file__).with_name("studio_remaster.py")),
                   str(root / REMASTER), str(work / "picture.mp4"), str(info["fps"]),
                   *ff, *source(start), "-t", str(duration), "-map", f"0:{info['videoIndex']}",
                   "-fps_mode", "passthrough", "-enc_time_base", "demux", "-pix_fmt", "rgb24", "-c:v", "rawvideo",
                   "-threads", "2", "-f", "nut", "pipe:1"], work)
        await run(ff + ["-i", str(work / "picture.mp4"), *source(start), "-map", "0:v:0",
                        "-map", "1:a:0?", "-c:v", "copy", "-t", str(duration), *finish], work)
        return
    if masked:
        hints = points or ([(*point,1)] if point else [])
        if (not (selection or box or any(p[2] == 1 for p in hints)) or any(not 0 <= v <= 1 for p in hints for v in p)
                or box and (not all(0 <= v <= 1 for v in box) or box[0]>=box[2] or box[1]>=box[3])):
            raise ValueError("Select the subject in the clip.")
        fps, sw, sh = shot_geometry(info)
        anchor = start if anchor is None else anchor
        if not start <= anchor < end:
            raise ValueError("Reference frame is outside the selected clip.")
        if shutil.disk_usage(work).free < sw*sh*7*math.ceil(duration*fps) + 512*1024**2:
            raise ValueError("Not enough free disk space.")
        frames = work / "frames"
        frames.mkdir()
        w, h = info["width"], info["height"]
        if selection:
            save_selection(selection, work, (sw, sh))
        await run(ff + source(start) + ["-t", str(duration), "-map", f"0:{info['videoIndex']}",
                  "-vf", f"fps={fps},scale={sw}:{sh}", "-threads", "2", str(frames / "%08d.png")], work)
        paths = sorted(frames.glob("*.png"))
        if not paths:
            raise ValueError("Could not decode the selected frame.")
        pivot = min(len(paths)-1, round((anchor-start)*fps))
        (work/"targets.json").write_text(json.dumps({"points":hints,"box":box,"pivot":pivot}),encoding="ascii")
        # The click can fall between inference samples. Initialize with exactly the picture shown in the picker.
        if selection:
            raw = await asyncio.to_thread(selection_frame,info["path"],info["videoIndex"],anchor,fps,sw,sh)
            if not raw:
                raise ValueError("Could not decode the selected frame.")
            (work/"anchor.png").write_bytes(raw)
        worker = [sys.executable, str(Path(__file__).with_name("video_edit_mask_worker.py")), str(root), str(work)]
        await run(worker + ["track"], work)
        await render_windows(paths, root, work, run)
        # Composite against the original at its native dimensions, not the downscaled inference input.
        ow, oh = w+w%2, h+h%2
        cmd = ff + source(start)
        sequence = "effect/%08d.png"
        cmd += ["-framerate", str(fps), "-i", str(work / sequence),
                "-framerate", str(fps), "-i", str(work / "masks/%08d.png")]
        filt = (f"[0:{info['videoIndex']}]fps={info['fps']},scale={ow}:{oh},setsar=1[base];"
                f"[1:v]scale={ow}:{oh},setsar=1[fg];[2:v]format=gray,dilation,dilation,dilation,dilation,scale={ow}:{oh}[a];")
        filt += "[fg][a]alphamerge[layer];[base][layer]overlay[out]"
        await run(cmd + ["-filter_complex", filt, "-map", "[out]", "-map", "0:a:0?", "-t", str(duration), *encode, *finish], work)
        return
    if action in ("vocals", "instrumental"):
        if not info["audio"]:
            raise ValueError("This clip has no audio track.")
        pcm = ["-ar", "44100", "-ac", "2", "-f", "f32le"]
        await run(ff + source(start) + ["-t", str(duration), "-map", "0:a:0", *pcm, "mix.raw"], work)
        await run([sys.executable, str(Path(__file__).with_name("video_edit_mdx.py")), str(root / MDX),
                   "mix.raw", "stem.raw", action], work)
        await run(ff + source(start) + pcm + ["-i", "stem.raw", "-map", f"0:{info['videoIndex']}", "-map", "1:a:0",
                  "-t", str(duration), "-vf", "pad=ceil(iw/2)*2:ceil(ih/2)*2", *encode, *finish], work)
        return

    if info["width"] * info["height"] > 1920 * 1080:
        raise ValueError("Frame interpolation supports clips up to 1080p.")
    fps = min(60, max(1, round(info["fps"])))
    if fps >= 60:
        raise ValueError("This clip is already at 60 FPS or higher.")
    target = 60
    count = max(1, round(duration * fps))
    part_names = []
    for index in range(0, count, fps):
        n = min(count - index, fps)
        # Include the next frame as lookahead, but encode it only in the next batch.
        with tempfile.TemporaryDirectory(dir=work) as frames:
            tmp = Path(frames)
            src, out = tmp / "input", tmp / "output"
            src.mkdir()
            out.mkdir()
            await run(ff + source(start + index / fps) + ["-map", f"0:{info['videoIndex']}", "-vf", f"fps={fps}",
                      "-frames:v", str(n + int(index + n < count)), "-threads", "2", str(src / "%08d.png")], work)
            names = sorted(src.glob("*.png"))
            if not names:
                raise ValueError("Could not decode the selected frames.")
            if len(names) == 1:
                shutil.copyfile(names[0], src / "00000002.png")
            size = max(2, len(names))
            await run([str(root / "rife-ncnn-vulkan.exe"), "-i", str(src), "-o", str(out), "-m",
                       str(root / "rife-v4.6"), "-n", str(max(2, round(size * target / fps))),
                       "-j", "2:1:2", "-f", "%08d.png"], work)
            part = f"part{index:06}.mp4"
            await run(ff + ["-framerate", str(target), "-i", str(out / "%08d.png"), "-frames:v",
                      str(max(1, round((index+n)*target/fps)-round(index*target/fps))),
                      "-vf", "pad=ceil(iw/2)*2:ceil(ih/2)*2", *encode, part], work)
            part_names.append(part)
    (work / "parts.txt").write_text("".join(f"file '{p}'\n" for p in part_names), encoding="ascii")
    cmd = ff + ["-f", "concat", "-safe", "1", "-i", "parts.txt", *source(start), "-map", "0:v:0", "-map", "1:a:0?",
                "-c:v", "copy", "-t", str(duration)]
    await run(cmd + finish, work)


def render_ranges(count, limit):
    # Balance windows so a tail of 1-2 frames never becomes a separate inference.
    overlap = 4
    windows = 1 if count <= limit else math.ceil(count/(limit-2*overlap))
    for i in range(windows):
        first, stop = i*count//windows, (i+1)*count//windows
        yield first, stop, max(0,first-overlap), min(count,stop+overlap)


def link_frame(src, dst):
    try:
        os.link(src,dst)
    except OSError:
        shutil.copyfile(src,dst)


async def render_windows(paths, root, work, run):
    dest = work/"effect"
    dest.mkdir()
    for first, stop, left, right in render_ranges(len(paths), 120):
        with tempfile.TemporaryDirectory(dir=work) as scratch:
            part = Path(scratch)
            (part/"masks").mkdir()
            (part/"frames").mkdir()
            for k in range(max(3,right-left)):
                frame = paths[min(left+k,right-1)]
                name = f"{k+1:08}.png"
                link_frame(frame,part/"frames"/name)
                link_frame(work/"masks"/frame.name,part/"masks"/name)
            await run([sys.executable,str(Path(__file__).with_name("video_edit_mask_worker.py")),str(root),str(part),"erase"],part)
            results = sorted((part/"painted/frames/frames").glob("*.png"))
            if len(results) != max(3,right-left):
                raise ValueError("Could not render all selected frames.")
            for idx in range(first,stop):
                results[idx-left].replace(dest/paths[idx].name)
