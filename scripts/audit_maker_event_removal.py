"""Check source-time landmarks independently annotated from videoteste/teste.mp4."""

import json
import sys
from pathlib import Path

import av
import numpy as np


def audio(path):
    with av.open(str(path)) as media:
        resampler = av.AudioResampler(format="flt", layout="mono", rate=8000)
        samples = [p.to_ndarray().ravel() for f in media.decode(audio=0) for p in resampler.resample(f)]
        return np.concatenate(samples)


def compare_picture(source, output, clips):
    def pixels(frame):
        return frame.reformat(width=48, height=27, format="gray").to_ndarray().astype(np.int16)

    with av.open(str(source)) as media:
        pts, frames = zip(*[(frame.time, pixels(frame)) for frame in media.decode(video=0)])
    pts = np.array(pts)
    errors, i = [], 0
    with av.open(str(output)) as media:
        for frame in media.decode(video=0):
            while i + 1 < len(clips) and clips[i + 1]["at"] <= frame.time:
                i += 1
            position = clips[i]["start"] + frame.time - clips[i]["at"]
            index = np.searchsorted(pts, position)
            sample = pixels(frame)
            errors.append(min(np.abs(sample - f).mean() for f in frames[max(0, index - 5) : index + 5]))
    print("Decoded luma MAE (median, p95, out of 255):", np.percentile(errors, [50, 95]).round(2))
    assert np.percentile(errors,95) < 4, "Rendered picture deviates from the selected source ranges"


def main():
    edit = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    clips = edit["clips"]
    # Contact / striking motion, not the static injury seen in adjacent dialogue.
    strikes = [
        24.2,
        27.4,
        28.2,
        33.0,
        34.2,
        35.4,
        40.2,
        45.2,
        45.8,
        47.2,
        50.8,
        55.6,
        58.6,
        62.4,
        65.8,
        67.2,
        69.6,
        71.8,
    ]
    controls = [
        1,
        4.8,
        8.5,
        11,
        14.5,
        17,
        20.7,
        22.5,
        26,
        30,
        36.8,
        38,
        41.8,
        48.4,
        53.5,
        57.4,
        60.4,
        75.8,
        85,
        94,
    ]

    def retained(t):
        return any(c["start"] <= t < c["end"] for c in clips)

    assert all(a["end"] <= b["start"] for a, b in zip(clips, clips[1:]))
    assert all(not c["audioOnly"] and c["gain"] == 1 and c["motion"] == "none" for c in clips)
    assert not edit["captions"] and not edit["title"]
    print("Still visible at source times:", [t for t in strikes if retained(t)], "out of", len(strikes))
    print("Unrelated checkpoints removed:", [t for t in controls if not retained(t)], "out of", len(controls))
    assert clips[0]["start"] == 0 and clips[0]["end"] >= 23.5, "Unrelated cut in the opening"
    assert all(not retained(t) for t in strikes), "An annotated impact was retained"
    assert all(retained(t) for t in controls), "An unrelated checkpoint was removed"
    if len(sys.argv) > 2:
        compare_picture(sys.argv[2], Path(sys.argv[1]).with_name("result.mp4"), clips)
        before = audio(sys.argv[2])
        after = audio(Path(sys.argv[1]).with_name("result.mp4"))
        scores = []
        for c in clips:
            mid = (c["end"] - c["start"]) / 2
            if mid < 0.35:
                continue
            idx = int(8000 * (c["start"] + mid))
            out = int(8000 * (c["at"] + mid))
            ref = before[idx - 800 : idx + 800].astype(np.float64)
            sample = after[out - 2400 : out + 2400].astype(np.float64)
            if np.linalg.norm(ref) > 0.01:
                power = np.convolve(sample**2, np.ones(len(ref)), mode="valid")
                scores.append(
                    max(
                        np.correlate(sample, ref, mode="valid")
                        / np.sqrt(np.maximum(1e-12, power * np.dot(ref, ref)))
                    )
                )
        print("Audio correlation per retained excerpt:", [round(float(s), 2) for s in scores])
        assert scores and min(scores) > .7, "Retained sound does not match the source"


if __name__ == "__main__":
    main()
