"""Isolated SDR restoration worker. The decoder pipe carries original frame timestamps."""
import os
import subprocess
import sys
from fractions import Fraction

import av
import numpy as np
import torch
from torch import nn


class Residual(nn.Module):
    def __init__(self, channels):
        super().__init__()
        def conv():
            return nn.Conv2d(channels, channels, 3, padding=1, bias=False)
        self.res = nn.Sequential(conv(), nn.ReLU(), conv())

    def forward(self, x):
        return x + self.res(x)


class Student(nn.Module):
    def __init__(self):
        super().__init__()
        self.m_head = nn.Conv2d(3, 16, 3, padding=1, bias=False)
        for level, c in enumerate((16, 32, 64), 1):
            setattr(self, f"m_down{level}", nn.Sequential(
                Residual(c), Residual(c), nn.Conv2d(c, 2*c, 2, stride=2, bias=False)))
            setattr(self, f"m_up{level}", nn.Sequential(
                nn.ConvTranspose2d(2*c, c, 2, stride=2, bias=False), Residual(c), Residual(c)))
        self.m_body = nn.Sequential(Residual(128), Residual(128))
        self.m_tail = nn.Conv2d(16, 3, 3, padding=1, bias=False)

    def forward(self, x):
        skip = [self.m_head(x)]
        for layer in (self.m_down1, self.m_down2, self.m_down3):
            skip.append(layer(skip[-1]))
        x = self.m_body(skip[-1])
        for layer in (self.m_up3, self.m_up2, self.m_up1, self.m_tail):
            x = layer(x + skip.pop())
        return x


@torch.inference_mode()
def restore(frame, model, tile=768):
    h, w = frame.shape[:2]
    padded = np.pad(frame, ((0, -h % 8), (0, -w % 8), (0, 0)), mode="edge")
    result = np.empty_like(frame)
    param = next(model.parameters())
    # Align tiles to all three encoder strides; discard the contextual border.
    for y in range(0, h, tile):
        for x in range(0, w, tile):
            top, left = max(0, y-96), max(0, x-96)
            patch = padded[top:y+tile+96, left:x+tile+96]
            tensor = torch.from_numpy(patch).permute(2,0,1).unsqueeze(0).to(param).div_(255)
            out = model(tensor)[0, :, y-top:y-top+min(tile,h-y), x-left:x-left+min(tile,w-x)]
            result[y:y+tile, x:x+tile] = out.clamp(0,1).mul_(255).round_().byte().permute(1,2,0).cpu().numpy()
    return result


def process(weights, destination, fps, decoder):
    torch.set_num_threads(min(os.cpu_count() or 1, 4))
    model = Student().eval()
    model.load_state_dict(torch.load(weights, map_location="cpu", weights_only=True)["params"])
    if torch.cuda.is_available() and torch.cuda.mem_get_info()[0] >= 512*1024**2:
        model.to(device="cuda", dtype=torch.float16, memory_format=torch.channels_last)
    child = subprocess.Popen(decoder, stdout=subprocess.PIPE, creationflags=0x08000000 if os.name=="nt" else 0)
    class DecoderPipe:
        # Windows pipe handles can claim to support seeks; libav must not probe by seeking.
        read = child.stdout.read

    try:
        with av.open(DecoderPipe(), format="nut") as source, av.open(destination, "w") as output:
            stream = None
            for frame in source.decode(video=0):
                if stream is None:
                    stream = output.add_stream("libx264", rate=Fraction(fps).limit_denominator(1001000))
                    stream.width, stream.height = frame.width+frame.width%2, frame.height+frame.height%2
                    stream.pix_fmt = "yuv420p"
                    stream.codec_context.time_base = Fraction(1,90000)
                    stream.codec_context.colorspace = 1  # ITU-R BT.709 matrix
                    stream.codec_context.sample_aspect_ratio = source.streams.video[0].sample_aspect_ratio or Fraction(1)
                    stream.options = {"crf":"15","preset":"veryfast","threads":"4"}
                rgb = frame.to_ndarray(format="rgb24")
                try:
                    enhanced = restore(rgb, model)
                except torch.cuda.OutOfMemoryError:
                    model.to(device="cpu", dtype=torch.float32)
                    enhanced = None
                if enhanced is None:
                    torch.cuda.empty_cache()
                    enhanced = restore(rgb, model)
                if frame.height%2 or frame.width%2:
                    enhanced = np.pad(enhanced, ((0,frame.height%2),(0,frame.width%2),(0,0)), mode="edge")
                picture = av.VideoFrame.from_ndarray(enhanced, format="rgb24").reformat(format="yuv420p",dst_colorspace="ITU709")
                picture.pts, picture.time_base = frame.pts, frame.time_base
                output.mux(stream.encode(picture))
            if stream is None:
                raise ValueError("No readable video frames.")
            output.mux(stream.encode())
        if child.wait():
            raise ValueError("Could not decode the selected frames.")
    finally:
        child.stdout.close()
        if child.poll() is None:
            child.kill()
            child.wait()


if __name__ == "__main__":
    process(*sys.argv[1:4], sys.argv[4:])
