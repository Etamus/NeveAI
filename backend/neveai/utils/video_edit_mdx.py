"""Local two-stem inference using UVR's Inst HQ 3 ONNX model."""
import sys


def separate(model, source, destination, vocals):
    import numpy as np
    import onnxruntime as ort
    import torch

    torch.set_num_threads(2)
    opts = ort.SessionOptions()
    opts.intra_op_num_threads = 4
    opts.inter_op_num_threads = 1
    session = ort.InferenceSession(str(model), opts, providers=["CPUExecutionProvider"])
    name = session.get_inputs()[0].name
    samples = np.memmap(source, dtype="<f4", mode="r").reshape(-1, 2)
    fft, hop, length = 6144, 1024, 255 * 1024
    margin = 16 * hop
    step = length - 2 * margin
    window = torch.hann_window(fft)
    with open(destination, "wb") as out, torch.inference_mode():
        for start in range(0, len(samples), step):
            left = max(0, start - margin)
            right = min(len(samples), start + length - margin)
            n = min(step, len(samples) - start)
            # Exact digital silence, including both overlap margins, has no signal to separate.
            if not samples[left:right].any():
                out.seek(n * 2 * 4, 1)
                continue
            offset = left - start + margin
            wave = torch.zeros(2, length)
            wave[:, offset:offset + right - left] = torch.from_numpy(samples[left:right].T.copy())
            spec = torch.stft(wave, fft, hop, window=window, return_complex=True)
            tensor = torch.view_as_real(spec[:, :3072]).permute(0, 3, 1, 2).reshape(1, 4, 3072, 256).contiguous()
            tensor[:, :, :3] = 0
            pred = torch.from_numpy(session.run(None, {name: tensor.numpy()})[0])
            spec.zero_()
            spec[:, :3072] = torch.view_as_complex(pred.reshape(2, 2, 3072, 256).permute(0, 2, 3, 1).contiguous())
            stem = torch.istft(spec, fft, hop, window=window, length=length) * 1.022
            target = (wave - stem if vocals else stem)[:, margin:margin+n]
            target.T.contiguous().numpy().astype("<f4", copy=False).tofile(out)
        out.truncate()


if __name__ == "__main__":
    separate(*sys.argv[1:4], sys.argv[4] == "vocals")
