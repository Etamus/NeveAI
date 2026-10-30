"""Small synthetic fixtures, no model or GPU generation."""
import argparse
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("kind", choices=("video", "pdf"))
args = parser.parse_args()
folder = Path(__file__).resolve().parents[1] / "logs/webview2-native-test"
folder.mkdir(parents=True, exist_ok=True)
if args.kind == "video":
    import av
    import numpy as np
    with av.open(str(folder / "probe.mp4"), "w") as output:
        stream = output.add_stream("libx264", rate=10)
        stream.width, stream.height, stream.pix_fmt = 160, 96, "yuv420p"
        for index in range(10):
            pixels = np.empty((96, 160, 3), dtype=np.uint8)
            pixels[:, :, :] = (40 + index * 15, 130, 170)
            frame = av.VideoFrame.from_ndarray(pixels, format="rgb24")
            for packet in stream.encode(frame):
                output.mux(packet)
        for packet in stream.encode():
            output.mux(packet)
else:
    import fitz
    with fitz.open() as document:
        page = document.new_page(width=400, height=300)
        page.insert_text((50, 100), "Native PDF preview", fontsize=22)
        document.save(folder / "probe.pdf")
