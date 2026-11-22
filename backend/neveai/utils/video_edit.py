"""Local, non-destructive editing primitives. All edit times are in the source media."""
import math
from bisect import bisect_right
import re
from functools import lru_cache
from pathlib import Path
from typing import Literal

import av
import regex
from pydantic import BaseModel, Field, field_validator

MAX_DURATION = 5 * 3600
MAX_CLIPS = 8192
MAX_CAPTIONS = 32768
CAPTION_LIMIT = 180
GRAPHEME = regex.compile(r"\X")
FORMATS = "mov,mp4,m4a,3gp,3g2,mj2,matroska,webm,avi,mpegts,mpeg,flv,ogg"
INPUT_OPTIONS = {"protocol_whitelist": "file", "format_whitelist": FORMATS}


class ColorValues(BaseModel):
    contrast: float = Field(ge=.85, le=1.2)
    brightness: float = Field(ge=-.08, le=.08)
    saturation: float = Field(ge=.85, le=1.18)

class ColorSample(ColorValues):
    time: float = Field(ge=0, le=MAX_DURATION+1)


class Grade(ColorValues):
    samples: list[ColorSample] = Field(default_factory=list, max_length=16)

    def filter(self, offset):
        def expression(name):
            points = sorted(self.samples, key=lambda p: p.time)
            if len(points) < 2:
                return str(getattr(self, name))
            value = str(getattr(points[0], name))
            for a,b in zip(points,points[1:]):
                delta = getattr(b,name)-getattr(a,name)
                if abs(delta) > .001 and b.time > a.time:
                    value += f"+({delta:.5f})*clip((t+({offset-a.time:.5f}))/{b.time-a.time:.5f},0,1)"
            return value
        return ",eq=" + ":".join(f"{p}='{expression(p)}'" for p in ("contrast","brightness","saturation")) + ":eval=frame"


class Clip(BaseModel):
    opacity: float = Field(default=1, ge=0, le=1)
    grade: Grade | None = None
    asset: str
    start: float = Field(ge=0)
    end: float = Field(gt=0, le=MAX_DURATION + 1)
    zoom: float = Field(default=1, ge=1, le=2.5)
    gain: float = Field(default=1, ge=0, le=2)
    at: float | None = Field(default=None, ge=0, le=MAX_DURATION)
    lane: int = Field(default=0, ge=0, le=5)
    noAudio: bool = False
    audioOnly: bool = False
    effect: Literal["none", "vivid", "cinema", "mono", "fade"] = "none"
    motion: Literal["none", "push", "whip", "glitch", "dip", "flash"] = "none"
    layout: Literal["full", "inset", "left", "right", "dissolve"] = "full"


CaptionFont = Literal["Arial", "Georgia", "Consolas", "Segoe UI", "Tahoma", "Verdana", "Trebuchet MS", "Times New Roman", "Impact"]
CaptionTheme = Literal["outline", "box", "highlight"]


class CueAppearance(BaseModel):
    font: CaptionFont | None = None
    size: int | None = Field(default=None, ge=12, le=36)
    theme: CaptionTheme | None = None


class Caption(BaseModel):
    speakerKey: str | None = Field(default=None,max_length=100)
    voiceSample: tuple[float,float] | None = None
    style: CueAppearance | None = None
    speakerName: str = Field(default='', max_length=80)
    horizontal: Literal['left','center','right'] | None = None
    position: Literal['top','center','bottom'] | None = None
    asset: str
    start: float = Field(ge=0)
    end: float = Field(gt=0, le=MAX_DURATION + 1)
    text: str = Field(min_length=1, max_length=4096)
    speechOnly: bool = False

    @field_validator("text")
    @classmethod
    def validate_caption_length(cls, text):
        if len(text) > CAPTION_LIMIT and len(GRAPHEME.findall(text)) > CAPTION_LIMIT:
            raise ValueError("Caption exceeds 180 characters")
        return text


class CaptionStyle(BaseModel):
    horizontal: Literal["left","center","right"] = "center"
    animation: Literal["none", "rise", "drop", "type", "pulse", "wave", "fade", "slide", "zoom", "blur", "spin"] = "none"
    position: Literal["top", "center", "bottom"] = "bottom"
    font: CaptionFont = "Arial"
    size: int = Field(default=18, ge=12, le=36)
    theme: CaptionTheme = "outline"


class Timeline(BaseModel):
    clips: list[Clip] = Field(min_length=1, max_length=MAX_CLIPS)
    captions: list[Caption] = Field(default_factory=list, max_length=MAX_CAPTIONS)
    height: int = Field(default=1080)
    normalize: bool = False
    captionStyle: CaptionStyle = Field(default_factory=CaptionStyle)
    aspect: Literal["source", "portrait", "landscape"] = "source"
    title: str | None = Field(default=None, max_length=80)


def positioned(clips):
    cursor = 0
    for clip in clips:
        if clip.at is None:
            yield cursor, clip
            cursor += clip.end - clip.start
        else:
            yield clip.at, clip


def layered(clips):
    return any(c.at is not None or c.lane or c.audioOnly for c in clips)


def layer_slices(clips, fps):
    items = list(positioned(clips))
    marks = sorted({0.0, *(round(t * fps) / fps for at, c in items for t in (at, at + c.end - c.start))})
    boundaries=iter(sorted((t,enter,i) for i,(at,c) in enumerate(items)
                           for t,enter in ((at,True),(at+c.end-c.start,False))))
    event=next(boundaries,None)
    live=set()
    for start, end in zip(marks, marks[1:]):
        center = (start + end) / 2
        while event and event[0]<=center:
            _,enter,i=event
            if enter: live.add(i)
            else: live.discard(i)
            event=next(boundaries,None)
        active = [items[i] for i in sorted(live)]
        video = sorted((item for item in active if not item[1].audioOnly and item[1].layout == "full"),
                       key=lambda item: item[1].lane)
        yield start, end, video[-1] if video else None, active


def probe(path, thumbnail=None):
    with av.open(str(path), options=INPUT_OPTIONS) as media:
        video = next((s for s in media.streams.video if s.duration), next(iter(media.streams.video), None))
        if video is None or not media.duration or not video.width or not video.height:
            raise ValueError("No readable video track.")
        duration = media.duration / av.time_base
        if not 0.1 <= duration <= MAX_DURATION or max(video.width, video.height) > 4096:
            raise ValueError("Use a video up to 5 hours and 4K.")
        frame = next(media.decode(video), None)
        if frame is None:
            raise ValueError("No readable video frames.")
        if thumbnail is not None:
            image = frame.to_image()
            image.thumbnail((280, 160))
            image.save(thumbnail, "JPEG", quality=78)
        rotation = float(video.metadata.get("rotate", "0"))
        for side in frame.side_data:
            if side.type.name == "DISPLAYMATRIX" and side.buffer_size >= 36:
                import numpy as np

                matrix = np.frombuffer(bytes(side), dtype="=i4", count=9)
                rotation = math.degrees(math.atan2(int(matrix[1]), int(matrix[0])))
                break
        width, height = video.width, video.height
        if abs(round(rotation / 90)) % 2:
            width, height = height, width
        return {
            "duration": round(duration, 3), "width": width, "height": height,
            "fps": round(float(video.average_rate or 30), 3), "audio": bool(media.streams.audio),
            "videoIndex": video.index,
            "browserReady": video.codec_context.name == "h264" and "mp4" in media.format.name
            and (not media.streams.audio or media.streams.audio[0].codec_context.name in {"aac", "mp3"}),
        }




@lru_cache(maxsize=1)
def whisper(root):
    from faster_whisper import WhisperModel

    from faster_whisper.utils import download_model
    from huggingface_hub.errors import LocalEntryNotFoundError
    try:
        model = download_model("turbo", cache_dir=root, local_files_only=True)
        if not (Path(model) / "model.bin").is_file():
            model = "base"
    except LocalEntryNotFoundError:
        model = "base"
    return WhisperModel(model, download_root=root, local_files_only=True, device="cpu", compute_type="int8", cpu_threads=4)


@lru_cache(maxsize=32)
def preview_waveform(path, duration, stopped=None):
    import numpy as np

    rate = 8000
    sample_limit = max(1, round(duration * rate))
    bucket_size = math.ceil(sample_limit / 240)
    peaks = [0.0] * 240
    cursor = 0
    resampler = av.AudioResampler(format="fltp", layout="mono", rate=rate)

    def collect(frame):
        nonlocal cursor
        samples = np.abs(frame.to_ndarray().reshape(-1))
        offset = 0
        while offset < len(samples) and cursor < sample_limit:
            bucket = cursor // bucket_size
            count = min(len(samples) - offset, (bucket + 1) * bucket_size - cursor)
            peaks[bucket] = max(peaks[bucket], min(1.0, float(samples[offset:offset + count].max()) * 2.5))
            cursor += count
            offset += count

    with av.open(str(path), options=INPUT_OPTIONS) as media:
        if not media.streams.audio:
            return []
        if duration > 300:
            # This is a 240-pixel overview, not audio analysis for editing/export.
            audio = media.streams.audio[0]
            for i in range(240):
                if stopped and stopped.is_set():
                    return []
                time = duration * (i + .5) / 240
                media.seek(int(time/audio.time_base)+(audio.start_time or 0),stream=audio)
                for frame in media.decode(audio):
                    if frame.pts is not None and float((frame.pts-(audio.start_time or 0))*audio.time_base) + frame.samples/frame.sample_rate < time:
                        continue
                    values = frame.to_ndarray()
                    scale = 1 if values.dtype.kind=='f' else float(2**(values.dtype.itemsize*8-1))
                    peaks[i] = min(1., float(np.abs(values.astype('float32')-(128 if values.dtype==np.uint8 else 0)).max())*2.5/scale)
                    break
            return peaks
        for frame in media.decode(audio=0):
            if stopped and stopped.is_set():
                return []
            for output in resampler.resample(frame):
                collect(output)
            if cursor >= sample_limit:
                break
        for output in resampler.resample(None):
            collect(output)
    return peaks


def analyze_audio(path, duration, root, with_text, single_words=False):
    import numpy as np
    from faster_whisper.audio import decode_audio
    from faster_whisper.vad import VadOptions, get_speech_timestamps

    audio = decode_audio(str(path), sampling_rate=16000)
    voiced = get_speech_timestamps(audio, VadOptions(min_speech_duration_ms=170, min_silence_duration_ms=650, speech_pad_ms=180))
    windows = [(span["start"] / 16000, min(duration, span["end"] / 16000)) for span in voiced]
    wave = [float(min(1, np.max(np.abs(block)) * 2.5)) if len(block) else 0 for block in np.array_split(audio, 240)]
    cues = []
    if with_text and windows:
        model = whisper(str(root))
        segments, _ = model.transcribe(audio, beam_size=5, vad_filter=True, word_timestamps=True, condition_on_previous_text=False)
        for segment in segments:
            group = []
            for word in segment.words or ():
                group.append(word)
                if single_words or len(group) >= 8 or len("".join(w.word for w in group)) >= 42 or word.word.rstrip().endswith((".", "?", "!")):
                    _caption(cues, group, duration)
                    group = []
            if group:
                _caption(cues, group, duration)
    blocks = audio[:len(audio)//1600*1600].reshape(-1, 1600)
    # 100 ms RMS for balancing a separate ambience bed against the selected dialogue.
    rms = np.sqrt(np.einsum("ij,ij->i", blocks, blocks) / 1600)
    return {"wave": wave, "cues": cues, "speech_windows": windows, "rms": rms}


def _caption(cues, words, duration):
    text = "".join(w.word for w in words).strip()
    if len(text) > CAPTION_LIMIT:
        text = "".join(GRAPHEME.findall(text)[:CAPTION_LIMIT])
    start = max(0, words[0].start)
    end = min(duration, max(start + .12, words[-1].end))
    if text and end > start:
        cues.append({"start": start, "end": end, "text": text})




def projected_captions(clips, captions, styled=False):
    by_asset={}
    for c in captions:
        by_asset.setdefault(c.asset,[]).append(c)
    ends={}
    for asset,items in by_asset.items():
        items.sort(key=lambda c:c.start)
        high=0
        ends[asset]=[]
        for c in items:
            high=max(c.end,high)
            ends[asset].append(high)
    def intersect(asset,left,right):
        items=by_asset.get(asset,())
        for i in range(bisect_right(ends.get(asset,()),left),len(items)):
            cue=items[i]
            if cue.start>=right: break
            if cue.end>left: yield cue
    def content(cue):
        text = f'{cue.speakerName}: {cue.text}' if cue.speakerName else cue.text
        if not styled:
            return (text,)
        fields = (text, cue.horizontal or '', cue.position or '')
        return (*fields, cue.style.font or '', cue.style.size or 0, cue.style.theme or '') if cue.style else fields

    for cue in captions:
        if cue.asset == "timeline" and cue.end > cue.start:
            yield cue.start, cue.end, *content(cue)
    if layered(clips):
        by_caption = {}
        for start, end, visible, active in layer_slices(clips, 1000):
            detached = [(at, clip) for at, clip in active if clip.audioOnly
                        and next(intersect(clip.asset,clip.start+start-at,clip.start+end-at),None) is not None]
            if detached:
                visible = max(detached, key=lambda entry: entry[1].gain)
            if not visible:
                continue
            offset, clip = visible
            for cue in intersect(clip.asset,clip.start+start-offset,clip.start+end-offset):
                a = max(start, offset + max(clip.start, cue.start) - clip.start)
                b = min(end, offset + min(clip.end, cue.end) - clip.start)
                if b - a < .04:
                    continue
                ranges = by_caption.setdefault((cue.asset, cue.start, cue.end, *content(cue)), [])
                if ranges and a - ranges[-1][1] <= .002:
                    ranges[-1] = (ranges[-1][0], b)
                else:
                    ranges.append((a, b))
        yield from sorted((a, b, *key[3:]) for key, ranges in by_caption.items() for a, b in ranges)
        return
    by_caption = {}
    for offset, clip in positioned(clips):
        if clip.audioOnly:
            continue
        for cue in intersect(clip.asset,clip.start,clip.end):
            start = offset + max(0, cue.start - clip.start)
            end = offset + min(clip.end, cue.end) - clip.start
            if end - start < .04:
                continue
            spans = by_caption.setdefault((cue.asset, cue.start, cue.end, *content(cue)), [])
            if spans and start - spans[-1][1] <= .002:
                spans[-1] = spans[-1][0], max(spans[-1][1], end)
            else:
                spans.append((start, end))
    yield from sorted((start, end, *key[3:]) for key, spans in by_caption.items() for start, end in spans)


def subtitle_filter(style):
    # libass force_style uses legacy SSA alignment values for SRT input.
    alignment = {"top": 6, "center": 10, "bottom": 2}[style.position]
    color = "&H005EE4FF" if style.theme == "highlight" else "&H00FFFFFF"
    box = "BorderStyle=3,Outline=3,OutlineColour=&H80000000" if style.theme == "box" else "BorderStyle=1,Outline=2"
    return (f"subtitles=captions.srt:force_style='FontName={style.font},FontSize={style.size},"
            f"PrimaryColour={color},{box},MarginV=24,Alignment={alignment}'")


def video_effect(effect, length):
    if effect == "fade":
        fade = min(.45, length / 3)
        return f",fade=t=in:st=0:d={fade:.4f},fade=t=out:st={length-fade:.4f}:d={fade:.4f}"
    return {"vivid": ",eq=saturation=1.34:contrast=1.10",
            "cinema": ",eq=saturation=0.82:contrast=1.16:brightness=-0.03",
            "mono": ",hue=s=0"}.get(effect, "")


def video_framing(width, height, fill):
    scale = "increase" if fill else "decrease"
    canvas = f"crop={width}:{height}" if fill else f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2"
    return f"scale={width}:{height}:force_original_aspect_ratio={scale}:force_divisible_by=2,{canvas},setsar=1,format=yuv420p"


def write_srt(path, cues):
    def stamp(seconds):
        sec, ms = divmod(round(seconds * 1000), 1000)
        minute, sec = divmod(sec, 60)
        hour, minute = divmod(minute, 60)
        return f"{hour:02}:{minute:02}:{sec:02},{ms:03}"

    with path.open("w", encoding="utf-8", newline="\n") as output:
        for index, (start, end, text) in enumerate(cues, 1):
            text = re.sub(r"[\r\n\x00-\x1f<>]", " ", text)
            output.write(f"{index}\n{stamp(start)} --> {stamp(end)}\n{text}\n\n")


def ffmpeg_binary():
    # Only use the executable from the installed wheel, without PATH/online fallbacks.
    import imageio_ffmpeg

    folder = Path(imageio_ffmpeg.__file__).parent / "binaries"
    return str(next(p for p in sorted(folder.glob("ffmpeg-*")) if p.is_file()))


def render_command(clips, assets, width, height, tempo, subtitles, normalize, fill=False, source_offset=0):
    from neveai.utils.video_edit_styles import motion_filter

    unique = list(dict.fromkeys(c.asset for c in clips))
    command = [ffmpeg_binary(), "-nostdin", "-hide_banner", "-loglevel", "error", "-y", "-progress", "pipe:1",
               "-filter_complex_threads", "2"]
    for key in unique:
        command += ["-threads", "2", "-protocol_whitelist", "file", "-format_whitelist", FORMATS, "-i", str(assets[key]["path"])]
    filters, join = [], []
    for i, clip in enumerate(clips):
        src = unique.index(clip.asset)
        info = assets[clip.asset]
        length = clip.end - clip.start
        # Scale/pad opens on the same framing as the sequence monitor.
        v = (f"[{src}:{info['videoIndex']}]trim=start={clip.start:.6f}:end={clip.end:.6f},setpts=PTS-STARTPTS,"
             f"fps={tempo},{video_framing(width, height, fill)}")
        if clip.zoom > 1:
            crop_w = max(2, int(width / clip.zoom) // 2 * 2)
            crop_h = max(2, int(height / clip.zoom) // 2 * 2)
            v += f",crop={crop_w}:{crop_h},scale={width}:{height}"
        filters.append(v + (clip.grade.filter(source_offset+clip.start) if clip.grade else "") + video_effect(clip.effect, length) + motion_filter(clip.motion, 0, width, height, tempo)
                       + (f",format=rgb24,colorchannelmixer=rr={clip.opacity}:gg={clip.opacity}:bb={clip.opacity}" if clip.opacity < 1 else "")
                       + f",tpad=stop_mode=clone:stop_duration={1/tempo:.6f},trim=duration={length:.6f}[v{i}]")
        if info["audio"] and not clip.noAudio:
            filters.append(f"[{src}:a:0]atrim=start={clip.start:.6f}:end={clip.end:.6f},"
                           f"asetpts=PTS-STARTPTS,aformat=sample_rates=48000:channel_layouts=stereo,"
                           f"volume={clip.gain},apad,atrim=duration={length:.6f}[a{i}]")
        else:
            filters.append(f"anullsrc=r=48000:cl=stereo,atrim=duration={length:.6f}[a{i}]")
        join.append(f"[v{i}][a{i}]")
    filters.append("".join(join) + f"concat=n={len(clips)}:v=1:a=1[video][audio]")
    video, audio = "[video]", "[audio]"
    if subtitles:
        filters.append("[video]subtitles=captions.srt:force_style='FontSize=18,Outline=2,MarginV=24,Alignment=2'[captioned]")
        video = "[captioned]"
    if normalize:
        filters.append("[audio]loudnorm=I=-16:TP=-1.5:LRA=9,aresample=48000[normalized]")
        audio = "[normalized]"
    return command, ";".join(filters), video, audio


def render_layer_command(start, length, visible, active, assets, width, height, fps, fill=False, *, audio_only=False):
    from neveai.utils.video_edit_styles import motion_filter

    cmd = [ffmpeg_binary(), "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
           "-progress", "pipe:1", "-filter_complex_threads", "2"]

    inputs = {}

    def source(at, clip):
        timing = max(clip.start, clip.start + start - at)
        key = (clip.asset, timing)
        if key in inputs:
            return inputs[key]
        cmd.extend([*(["-vn", "-sn", "-dn"] if audio_only else []), "-threads", "2", "-protocol_whitelist", "file", "-format_whitelist", FORMATS,
                    "-ss", f"{timing:.6f}", "-i", str(assets[clip.asset]["path"])])
        inputs[key] = len(inputs)
        return inputs[key]

    filters = []

    def audio_mix():
        sources = []
        for at, clip in active:
            if clip.noAudio or not clip.gain or not assets[clip.asset]["audio"]:
                continue
            index = source(at, clip)
            name = f"a{len(sources)}"
            filters.append(f"[{index}:a:0]asetpts=PTS-STARTPTS,aformat=sample_rates=48000:channel_layouts=stereo,"
                           f"volume={clip.gain},apad,atrim=duration={length:.6f}[{name}]")
            sources.append(f"[{name}]")
        if sources:
            filters.append("".join(sources) + f"amix=inputs={len(sources)}:normalize=0,alimiter=limit=0.95:level=0[audio]")
        else:
            filters.append(f"anullsrc=r=48000:cl=stereo,atrim=duration={length:.6f}[audio]")

    if audio_only:
        audio_mix()
        return cmd, ";".join(filters), None, "[audio]"

    def picture(at, clip, w, h, fill_frame):
        stream = source(at, clip)
        index = assets[clip.asset]["videoIndex"]
        video = f"[{stream}:{index}]setpts=PTS-STARTPTS,fps={fps},{video_framing(w, h, fill_frame)}"
        if clip.zoom > 1:
            video += f",crop={max(2, int(w/clip.zoom)//2*2)}:{max(2, int(h/clip.zoom)//2*2)},scale={w}:{h}"
        effect = clip.effect if clip.effect != "fade" or length >= clip.end - clip.start - 1/fps else "none"
        return (video + (clip.grade.filter(clip.start+max(0,start-at)) if clip.grade else "") + video_effect(effect, length) + motion_filter(clip.motion, max(0, start - at), w, h, fps)
                + f",tpad=stop_mode=clone:stop_duration={1/fps:.6f}")

    video = picture(*visible, width, height, fill) if visible else f"color=c=black:s={width}x{height}:r={fps}"
    if visible and visible[1].opacity < 1:
        stack = sorted(((at, c) for at, c in active if not c.audioOnly and c.layout == "full"), key=lambda p: p[1].lane)
        while len(stack) > 1 and any(c.opacity == 1 for _, c in stack[1:]):
            stack.pop(0)
        filters.append(f"color=c=black:s={width}x{height}:r={fps},trim=duration={length:.6f}[canvas0]")
        for i, (at, c) in enumerate(stack):
            filters.append(picture(at,c,width,height,fill) + f",format=rgba,colorchannelmixer=aa={c.opacity}[image{i}]")
            filters.append(f"[canvas{i}][image{i}]overlay=shortest=1[canvas{i+1}]")
        video = f"[canvas{len(stack)}]null"
    filters.append(video + f",trim=duration={length:.6f}[base]")
    layer = next(((at, clip) for at, clip in reversed(active)
                  if not clip.audioOnly and clip.layout != "full"), None)
    if layer:
        at, clip = layer
        layout = clip.layout
        x, y, w, h = 0, 0, width, height
        if layout == "inset":
            w, h = width * 19 // 100 * 2, height * 19 // 100 * 2
            x, y = width - w - width // 25, height // 25
        elif layout in ("left", "right"):
            w = width // 4 * 2
            x = width - w if layout == "right" else 0
        top = picture(at, clip, w, h, True)
        if layout == "dissolve":
            fade = min(.60, (clip.end - clip.start) / 2)
            tail = max(0, clip.end - clip.start - fade)
            top += (f",format=yuva420p,setpts=PTS+{max(0,start-at):.6f}/TB,"
                    f"fade=t=in:st=0:d={fade:.6f}:alpha=1,fade=t=out:st={tail:.6f}:d={fade:.6f}:alpha=1,setpts=PTS-STARTPTS")
        if clip.opacity < 1:
            top += f",format=rgba,colorchannelmixer=aa={clip.opacity}"
        filters.extend((top + "[layer]", f"[base][layer]overlay={x}:{y}:shortest=1[video]"))
    else:
        filters.append("[base]null[video]")
    audio_mix()
    return cmd, ";".join(filters), "[video]", "[audio]"
