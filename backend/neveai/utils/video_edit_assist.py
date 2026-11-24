"""Offline clip assistance. Run in a cancellable worker, outside the API process."""
import json
import subprocess
import sys
import wave
from pathlib import Path

import av
import numpy as np

from neveai.utils.video_edit import FORMATS, INPUT_OPTIONS, analyze_audio, ffmpeg_binary
from neveai.utils.studio_subtitles import compose_subtitles

BLOCK_SECONDS = 300
CONTEXT_SECONDS = 2


def audio_blocks(start,end,boundary=None):
    a=start
    while a<end:
        b=min(end,a+BLOCK_SECONDS)
        if boundary and b<end: b=boundary(a,b)
        yield a,b,max(start,a-CONTEXT_SECONDS),min(end,b+CONTEXT_SECONDS)
        a=b


def measure_grade(path, start, end):
    samples = []
    with av.open(str(path), options=INPUT_OPTIONS) as media:
        stream = media.streams.video[0]
        count = min(360,max(16,int(np.ceil((end-start)/45)))) if end-start>1800 else min(16,max(4,int(np.ceil((end-start)/2))))
        for t in np.linspace(start,end,count,endpoint=False)+(end-start)/(2*count):
            media.seek(int(t / stream.time_base), stream=stream)
            frame = next((f for f in media.decode(stream) if f.time is not None and f.time >= t), None)
            if frame is None:
                continue
            rgb = frame.reformat(width=96, height=64, format="rgb24").to_ndarray() / 255
            luma = rgb @ [.2126, .7152, .0722]
            lo, med, hi = np.percentile(luma, [5, 50, 95])
            if hi-lo > .06:
                samples.append([float(t), lo, med, hi, np.mean(rgb.max(axis=2)-rgb.min(axis=2))])
    if not samples:
        return {"brightness": 0, "contrast": 1, "saturation": 1}
    def values(lo, med, hi, chroma):
        return dict(brightness=round(float(np.clip((.45-med)*.28,-.08,.08)),4),
                contrast=round(float(np.clip(1+(.8-hi+lo)*.35,.85,1.2)),4),
                saturation=round(float(np.clip(1+(.19-chroma)*.5,.85,1.18)),4) if chroma > .025 else 1)
    # Keep the existing bounded FFmpeg curve; pool representative frames rather than increasing filter complexity.
    knots=[np.median(group,axis=0) for group in np.array_split(samples,min(16,len(samples)))]
    return {**values(*np.median(samples,axis=0)[1:]), "samples":[{"time":t, **values(*v)} for t,*v in knots]}


def transcription_gaps(start, end, covered):
    cursor, gaps = start, []
    for a,b in sorted(covered):
        a,b = max(start,a),min(end,b)
        if b<=a or b<=cursor:
            continue
        if a>cursor:
            gaps.append((cursor,a))
        cursor=b
    if end>cursor:
        gaps.append((cursor,end))
    return gaps


def extract_audio(path, start, end, target):
    subprocess.run([ffmpeg_binary(), "-nostdin", "-v", "error", "-y", "-protocol_whitelist", "file",
                    "-format_whitelist", FORMATS, "-ss", str(start), "-vn", "-i", str(path), "-t", str(end-start),
                    "-map", "0:a:0", "-ac", "1", "-ar", "16000", str(target)], check=True)


def digitally_silent(path):
    # Only skip exact PCM silence, never quiet speech.
    with wave.open(str(path),"rb") as stream:
        while chunk := stream.readframes(65536):
            if np.frombuffer(chunk,dtype="<i2").any():
                return False
    return True


def speaker_workers(blocks):
    if blocks < 4:
        return 1
    try:
        import psutil
        cores = psutil.cpu_count(logical=False) or 1
        headroom = psutil.virtual_memory().available - 3 * 1024**3
        return max(1, min(3, cores // 2, headroom // (1536 * 1024**2)))
    except (ImportError, OSError):
        return 1


def extract_speaker_window(session, path, block, wav):
    left, right, a, b = block
    session.observations.clear()
    extract_audio(path, a, b, wav)
    turns = [] if digitally_silent(wav) else session.turns(wav, a, left, right)
    return list(session.observations), turns


_speaker_engine = None


def speaker_worker(job):
    from tempfile import TemporaryDirectory
    from neveai.utils.video_edit_speakers import SessionSpeakers
    path, block, cache, work = job
    global _speaker_engine
    if _speaker_engine is None:
        _speaker_engine = SessionSpeakers(cache)
    with TemporaryDirectory(dir=work) as tmp:
        return extract_speaker_window(_speaker_engine, path, block, Path(tmp) / "audio.wav")


def speaker_evidence(path, blocks, cache, work, workers=None):
    from concurrent.futures import ProcessPoolExecutor
    from concurrent.futures.process import BrokenProcessPool
    from multiprocessing import get_context
    from neveai.utils.video_edit_speakers import SessionSpeakers
    observations, turns = [], []
    def append(result):
        obs, local = result
        base = len(observations)
        turns.extend((a,b,base+i) for a,b,i in local)
        observations.extend(obs)
    completed = 0
    workers = workers or speaker_workers(len(blocks))
    if workers > 1:
        try:
            with ProcessPoolExecutor(workers, mp_context=get_context("spawn")) as pool:
                for result in pool.map(speaker_worker, ((path,b,cache,work) for b in blocks)):
                    append(result)
                    completed += 1
        except (BrokenProcessPool, OSError, MemoryError):
            pass  # Resume in order, without rerunning successfully merged windows.
    if completed < len(blocks):
        session = SessionSpeakers(cache)
        for block in blocks[completed:]:
            append(extract_speaker_window(session, path, block, work / "trim.wav"))
    return observations, turns


def assist(path, start, end, operation, root, work, speaker_cache=None, plan=None):
    if operation == "color":
        return {"grade": measure_grade(path, start, end)}
    audio = work / "trim.wav"
    def quiet_boundary(left,right):
        # Prefer a 240 ms quiet interval before the cut; the ASR input also includes context on either side.
        a=max(left+(right-left)*.75,right-8)
        path_out=work/"boundary.wav"
        extract_audio(path,a,right,path_out)
        with wave.open(str(path_out),"rb") as f:
            pcm=np.frombuffer(f.readframes(f.getnframes()),dtype="<i2")
        frames=len(pcm)//320
        if frames<12: return right
        rms=np.mean(pcm[:frames*320].astype(np.float32).reshape(-1,320)**2,axis=1)
        pos=int(np.argmin(np.convolve(rms,np.ones(12)/12,mode="valid")))
        return a+(pos+6)*.02
    if operation == "speech":
        windows=[]
        for left,right,a,b in audio_blocks(start,end):
            extract_audio(path,a,b,audio)
            if digitally_silent(audio): continue
            for x,y in analyze_audio(audio,b-a,root,False)["speech_windows"]:
                x,y=max(left,a+x)-start,min(right,a+y)-start
                if y<=x: continue
                if windows and x<=windows[-1][1]+.0001: windows[-1][1]=max(y,windows[-1][1])
                else: windows.append([x,y])
        return {"cues":[], "speech":windows}
    plan = plan or {"gaps":[(start,end)],"existing":[]}
    cues = []
    full_audio = False
    for gap_start,gap_end in plan["gaps"]:
        for left,right,a,b in audio_blocks(gap_start,gap_end,quiet_boundary):
            if b-a < .04: continue
            full_audio = a==start and b==end
            extract_audio(path,a,b,audio)
            if digitally_silent(audio): continue
            data=analyze_audio(audio,b-a,root,True,True,studio_captions=True)
            for cue in data["cues"]:
                x,y=a+cue["start"],min(b,a+cue["end"])
                if not left <= (x+y)/2 < right: continue
                prev=cues[-1] if cues else None
                if left>gap_start and prev and x<prev["end"]-.04 and prev["text"].split()[-1:]==[cue["text"].strip()] and abs(x-left)<=CONTEXT_SECONDS:
                    continue
                cues.append({**cue,"start":x,"end":y,"_limit":gap_end})
    if operation == "speakers" and (cues or plan["existing"]):
        previews={}
        from neveai.utils.video_edit_speakers import identify, resolve_turns, label_words
        cache=speaker_cache or Path(root).parent.parent / "video_edit_speakers"
        ordered=sorted([*plan["existing"],*cues],key=lambda c:c["start"])
        if end-start<=BLOCK_SECONDS:
            if not full_audio: extract_audio(path,start,end,audio)
            local=[{**c,"start":c["start"]-start,"end":c["end"]-start} for c in ordered]
            cues=[{**c,"start":start+c["start"],"end":start+c["end"]} for c in identify(audio,local,cache,previews,start,plan.get("speakerCount"),group=False)]
        else:
            blocks=[]
            index=0
            for left,right,a,b in audio_blocks(start,end):
                while index<len(ordered) and ordered[index]["end"]<=left: index+=1
                if index==len(ordered): break
                if ordered[index]["start"]>=right: continue
                blocks.append((left,right,a,b))
            observations, turns = speaker_evidence(path, blocks, cache, work)
            turns=resolve_turns(observations,turns,plan.get("speakerCount"))
            if not turns: raise ValueError("No speakers detected.")
            cues=label_words(ordered,turns,previews,group=False)
        return {"cues":compose_subtitles(cues,end),"speech":[],"samples":previews}
    if operation=="captions":
        cues=compose_subtitles(cues,end)
    else:
        for c in cues:
            c.pop("_limit",None)
            c.pop("_space",None)
    return {"cues":cues,"speech":[]}


if __name__ == "__main__":
    source, start, end, operation, root, target, *cache = sys.argv[1:]
    output = Path(target)
    plan = json.loads(Path(cache[1]).read_text(encoding="utf8")) if len(cache)>1 else None
    output.write_text(json.dumps(assist(source,float(start),float(end),operation,root,output.parent,cache[0] if cache else None,plan)),encoding="utf8")
