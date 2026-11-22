"""Verify a single-source paper edit against its encoded audio and save a shot sheet."""
import argparse
import json
from pathlib import Path

import av
import numpy as np
from faster_whisper.audio import decode_audio
from PIL import Image, ImageDraw
from scipy.signal import correlate


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", type=Path)
    parser.add_argument("source", type=Path)
    parser.add_argument("--picture-before", type=float, help="Fixture time where channel end screen begins")
    parser.add_argument("--clean", action="store_true", help="Assert an untreated, captionless documentary cut")
    args = parser.parse_args()
    folder = args.directory
    edit = json.loads((folder / "edit.json").read_text(encoding="utf-8"))
    clips = edit["clips"]
    rendered = folder / "result.mp4"
    source = decode_audio(str(args.source), sampling_rate=8000)
    result = decode_audio(str(rendered), sampling_rate=8000)
    pictures = [c for c in clips if not c["audioOnly"] and c["layout"] == "full"]
    assert len(pictures) >= 2
    if args.picture_before:
        assert max(c["end"] for c in pictures) <= args.picture_before + .04, "Channel end card in picture cut"
    if args.clean:
        assert not edit["captions"] and not edit["title"]
        assert all(c["motion"] == c["effect"] == "none" and c["zoom"] == 1 for c in pictures)
    assert len(result) < len(source) * .8, "Not a condensed edit"
    assert max(c["end"] for c in pictures) - min(c["start"] for c in pictures) > len(result) / 8000
    matches = []
    for c in clips:
        if c["gain"] < .75 or c["end"] - c["start"] < .5:
            continue
        # For a sound bridge check *both* halves, including after the picture cuts away.
        for fraction in (.25, .75):
            t = (c["end"] - c["start"]) * fraction
            size = min(2000, int((c["end"] - c["start"]) * .2 * 8000))
            size -= size % 2
            mid = round((c["start"] + t) * 8000)
            query = source[mid-size//2:mid+size//2]
            if np.linalg.norm(query) < .03:
                continue
            expected = round((c["at"] + t) * 8000) - size // 2
            left = max(0, expected - 2400)
            window = result[left:expected+size+2400]
            cross = correlate(window, query, mode="valid", method="fft")
            energy = np.cumsum(np.r_[0., window.astype(float)**2])
            scores = cross / (np.linalg.norm(query) * np.sqrt(np.maximum(energy[size:] - energy[:-size], 1e-9)))
            best = int(np.argmax(scores))
            matches.append([round(float(scores[best]), 3), round((left + best - expected) / 8, 1)])
    assert matches and min(score for score, _ in matches) > .65, matches
    sheet = Image.new("RGB", (240 * 4, 164 * ((len(pictures)+3)//4)), "#181818")
    draw = ImageDraw.Draw(sheet)
    with av.open(str(rendered)) as video:
        index = 0
        for frame in video.decode(video=0):
            if index == len(pictures):
                break
            c = pictures[index]
            if frame.time < c["at"] + (c["end"] - c["start"]) / 2:
                continue
            x, y = index % 4 * 240, index // 4 * 164
            sheet.paste(frame.to_image().resize((238, 134)), (x, y))
            draw.text((x + 3, y + 137), f'{c["at"]:.1f}s | src {c["start"]:.1f}s | {c["motion"]}')
            index += 1
    assert index == len(pictures)
    sheet.save(folder / "shots.jpg")
    print("Audio checks (correlation, offset ms):", matches)
    print("Picture shots:", len(pictures), "audio layers:", sum(c["audioOnly"] for c in clips))


if __name__ == "__main__":
    main()
