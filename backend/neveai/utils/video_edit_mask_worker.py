"""Isolated workers for the optional non-commercial, local masking tools."""
import os
import json
import runpy
import sys
from pathlib import Path


def offline(event, args):
    if event in ("socket.connect", "socket.getaddrinfo"):
        raise RuntimeError("Network access is disabled during clip processing.")


def main():
    root, work = map(Path, sys.argv[1:3])
    job = sys.argv[3]
    sys.path.insert(0, str(root / "packages"))
    os.environ.update(HF_HUB_OFFLINE="1", MPLBACKEND="Agg")
    sys.addaudithook(offline)
    import numpy as np
    import torch
    from PIL import Image

    if not torch.cuda.is_available():
        raise ValueError("A CUDA GPU is required.")
    torch.set_num_threads(2)
    if torch.cuda.mem_get_info()[0] < 4 * 1024**3:
        raise ValueError("Not enough free GPU memory.")
    frames = sorted((work / "frames").glob("*.png"))
    masks = work / "masks"
    targets = {} if job=="erase" else json.loads((work/"targets.json").read_text(encoding="ascii"))
    pivot = targets.get("pivot",0)
    def walk():
        yield from enumerate(frames[pivot:])
        if pivot:
            yield from enumerate(reversed(frames[:pivot+1]))
    def picture(i,path):
        return work/"anchor.png" if not i and (work/"anchor.png").exists() else path
    if job == "track":
        initial = None
        if (work/"selection.png").is_file():
            with Image.open(work/"selection.png") as selected:
                initial = np.array(selected) > 0
        from transformers import Sam2VideoModel, Sam2VideoProcessor
        local = str(root / "sam2")
        proc = Sam2VideoProcessor.from_pretrained(local, local_files_only=True)
        model = Sam2VideoModel.from_pretrained(local, local_files_only=True).to("cuda").eval()
        masks.mkdir()
        with torch.inference_mode():
            for i, path in walk():
                if not i:
                    sess = proc.init_video_session(inference_device="cuda", video_storage_device="cpu")
                with Image.open(picture(i,path)) as im:
                    w, h = im.size
                    inputs = proc(images=im.convert("RGB"), return_tensors="pt").to("cuda")
                if not i and initial is not None:
                    proc.add_inputs_to_inference_session(sess, frame_idx=0, obj_ids=1, input_masks=initial)
                elif not i:
                    hints, box = targets["points"], targets["box"]
                    proc.add_inputs_to_inference_session(sess, frame_idx=0, obj_ids=1,
                        input_points=[[[[x*(w-1),y*(h-1)] for x,y,_ in hints]]] if hints else None,
                        input_labels=[[[label for _,_,label in hints]]] if hints else None,
                        input_boxes=[[[v*(h-1 if j%2 else w-1) for j,v in enumerate(box)]]] if box else None,
                        original_size=(h,w))
                pred = model(inference_session=sess, frame=inputs.pixel_values[0], frame_idx=i)
                mask = proc.post_process_masks([pred.pred_masks], original_sizes=[[h,w]], binarize=False)[0]
                a = (mask.squeeze() > 0).cpu().numpy().astype("uint8") * 255
                if not i and initial is not None:
                    a = initial.astype("uint8") * 255
                if not i and (not a.any() or a.mean() > 253):
                    raise ValueError("Select a more distinct subject.")
                Image.fromarray(a).save(masks / path.name)
                # Streaming uses the conditioning output and a finite history, never old RGB tensors.
                sess.processed_frames.pop(i,None)
                oldest = i - max(model.num_maskmem, model.config.max_object_pointers_in_encoder)
                sess.output_dict_per_obj[0]["non_cond_frame_outputs"].pop(oldest,None)
        return
    if job == "erase":
        repo = root / "propainter"
        os.chdir(repo)
        sys.path.insert(0, str(repo))
        sys.argv = ["inference_propainter.py", "-i", str(work / "frames"), "-m", str(masks),
                    "-o", str(work / "painted"), "--fp16", "--save_frames", "--subvideo_length", "32"]
        runpy.run_path(str(repo / sys.argv[0]), run_name="__main__")
        return
    raise ValueError("Unknown masking operation.")


if __name__ == "__main__":
    main()
