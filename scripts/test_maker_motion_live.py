"""Opt-in live test of visual action selection with no soundtrack or scene changes."""

import tempfile
from pathlib import Path

import av
import httpx
import numpy as np


def main():
    with (
        tempfile.TemporaryDirectory() as tmp,
        httpx.Client(
            base_url="http://localhost:8080/api/v1/video-edit", timeout=480, trust_env=False
        ) as client,
    ):
        path = Path(tmp) / "motion.mp4"
        with av.open(str(path), "w") as video:
            track = video.add_stream("libx264", rate=24)
            track.width, track.height, track.pix_fmt = 400, 224, "yuv420p"
            y, x = np.ogrid[:224, :400]
            for i in range(14 * 24):
                t = i / 24
                center = (
                    60
                    + 140 * max(0, min(2, t - 2))
                    - 140 * max(0, min(2, t - 6))
                    + 140 * max(0, min(2, t - 10))
                )
                pixels = np.full((224, 400, 3), 165, dtype=np.uint8)
                pixels[(x - center) ** 2 + (y - 112) ** 2 <= 26**2] = (10, 30, 230)
                for packet in track.encode(av.VideoFrame.from_ndarray(pixels, format="rgb24")):
                    video.mux(packet)
            for packet in track.encode():
                video.mux(packet)
        asset = (
            client.post("media", files={"file": (path.name, path.read_bytes(), "video/mp4")})
            .raise_for_status()
            .json()
        )
        response = client.post(
            "plan",
            json={
                "prompt": "Remova os momentos em que o circulo azul se move para a direita.",
                "clips": [{"asset": asset["id"], "start": 0, "end": 14}],
            },
        )
        print(response.status_code, response.text, flush=True)
        clips = response.raise_for_status().json()["clips"]

        def present(t):
            return any(c["start"] <= t < c["end"] for c in clips)

        assert not any(present(t) for t in [2.5, 3.5, 10.5, 11.5])
        assert all(present(t) for t in [1, 5, 6.5, 7.5, 9, 13])


if __name__ == "__main__":
    main()
