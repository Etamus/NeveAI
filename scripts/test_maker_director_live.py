"""Exercise the running Maker with local vision inference and audit encoded frames."""
import json
import os
import re
import time
from pathlib import Path

import av
import httpx
import numpy as np


def request(client, path, **kwargs):
    response = client.post(path, **kwargs)
    response.raise_for_status()
    return response.json()


def main():
    origin = os.getenv("NEVE_TEST_ORIGIN", "http://localhost:8080")
    output = Path(os.getenv("NEVE_TEST_OUTPUT", "logs/maker-director-live"))
    output.mkdir(parents=True, exist_ok=True)
    sample = Path(os.getenv("NEVE_TEST_VIDEO", "videoteste/teste.mp4"))
    prompt = os.getenv("NEVE_TEST_EDIT", (
        "Faça uma montagem curta de 15 a 25 segundos com falas marcantes dos personagens. "
        "Abra com um trecho mais adiante do vídeo, volte para uma fala anterior e finalize com outra cena. "
        "Selecione pelo que é dito e pelo que aparece, sem inventar falas. Legende o diálogo e "
        "sobreponha uma segunda cena no canto em pelo menos um momento, sem interromper a fala. "
        "Use um glitch e um flash em momentos diferentes, com intenção. Título curto: 'Frases de efeito'."
    ))
    with httpx.Client(base_url=origin, timeout=500, trust_env=False) as client:
        with sample.open("rb") as stream:
            asset = request(client, "/api/v1/video-edit/media", files={"file": (sample.name, stream, "video/mp4")})
        print("media", asset, flush=True)
        start = time.monotonic()
        edit = None
        with client.stream("POST", "/api/v1/video-edit/plan/progress", json={"prompt": prompt, "height": 720,
                           "clips": [{"asset": asset["id"], "start": 0, "end": asset["duration"]}]}) as response:
            response.raise_for_status()
            for line in response.iter_lines():
                row = json.loads(line)
                if "progress" in row:
                    print(round(time.monotonic() - start, 2), row["progress"], flush=True)
                elif "error" in row:
                    raise RuntimeError(row["error"])
                else:
                    edit = row["result"]
        assert edit
        plan_seconds = time.monotonic() - start
        (output / "edit.json").write_text(json.dumps(edit, ensure_ascii=False, indent=2), encoding="utf-8")
        print("edit", edit["summary"], [(c["start"], c["end"], c["at"], c["layout"], c["motion"]) for c in edit["clips"]], flush=True)
        if "NEVE_TEST_EDIT" not in os.environ:
            base = [c for c in edit["clips"] if c["layout"] == "full" and not c["audioOnly"]]
            assert any(a["start"] > b["start"] for a, b in zip(base, base[1:])), "Source order did not change"
            assert any(c["layout"] == "inset" for c in edit["clips"]), "No inset requested composition"
            assert {"glitch", "flash"} <= {c["motion"] for c in edit["clips"]}
            assert edit["captions"]
        start = time.monotonic()
        job = request(client, "/api/v1/video-edit/exports", json=edit)
        home = f"/api/v1/video-edit/exports/{job['id']}"
        while job["status"] in ("queued", "exporting"):
            time.sleep(.4)
            job = client.get(home).raise_for_status().json()
        assert job["status"] == "done", job
        rendered = output / "result.mp4"
        rendered.write_bytes(client.get(home + "/mp4").raise_for_status().content)
        if job["captions"]:
            captions = client.get(home + "/srt").raise_for_status().text
            assert " --> " in captions, captions
            last_start = 0
            caption_count = 0
            for a, b in re.findall(r"(\d\d:\d\d:\d\d,\d{3}) --> (\d\d:\d\d:\d\d,\d{3})", captions):
                def seconds(stamp):
                    return sum(float(item.replace(",", ".")) * 60 ** i for i, item in enumerate(reversed(stamp.split(":"))))
                start_time, end_time = seconds(a), seconds(b)
                assert last_start <= start_time < end_time
                last_start = start_time
                caption_count += 1
            (output / "result.srt").write_text(captions, encoding="utf-8")
        else:
            caption_count = 0
        encode_seconds = time.monotonic() - start
    with av.open(str(rendered)) as video:
        frame_pts = []
        dark = 0
        image_checks = []
        for frame in video.decode(video=0):
            frame_pts.append(frame.time)
            pixels = frame.reformat(width=80, height=48, format="gray").to_ndarray()
            dark += int(pixels.max() < 22)
            if os.getenv("NEVE_TEST_EXPECT_COLORS"):
                rgb = frame.reformat(width=80, height=48).to_ndarray(format="rgb24")
                image_checks.append((frame.time, int(rgb[24, 22].argmax()), int(rgb[6, 69].argmax())))
        assert len(frame_pts) >= 30 and all(a < b for a, b in zip(frame_pts, frame_pts[1:]))
        assert dark < max(2, len(frame_pts) * .08)
        if image_checks:
            center = [value[1] for value in image_checks]
            assert center[2] == 2 and center[-3] == 0 and 1 not in center
            assert any(inside == 0 and inset == 1 for _, inside, inset in image_checks)
    with av.open(str(rendered)) as media:
        frames = list(media.decode(audio=0))
        sound = np.concatenate([frame.to_ndarray().ravel() for frame in frames])
        assert np.max(np.abs(sound)) > .01 and all(a.time < b.time for a, b in zip(frames, frames[1:]))
        duration = max(c["at"] + c["end"] - c["start"] for c in edit["clips"])
        assert abs(media.duration / av.time_base - duration) < .25
    results = {"plan_seconds": plan_seconds, "export_seconds": encode_seconds, "frames": len(frame_pts),
               "dark_frames": dark, "audio_frames": len(frames), "caption_cues": caption_count, "duration": duration}
    (output / "audit.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(results, flush=True)


if __name__ == "__main__":
    main()
