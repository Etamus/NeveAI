"""Offline diagnostic transcription; recognition is evidence, not ground-truth audio scoring."""
import json
from pathlib import Path

from faster_whisper import WhisperModel

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "logs/video-sweetspot-20261102"
snapshots = ROOT / "backend/data/cache/whisper/models/models--Systran--faster-whisper-base/snapshots"
model_path = next(path for path in snapshots.iterdir() if (path / "model.bin").is_file())
model = WhisperModel(str(model_path), device="cpu", compute_type="int8", cpu_threads=2,
                     local_files_only=True)
results = []
for name in ["h3-480-vlog", "h3-w6-480-vlog", "vdn-480-vlog", "h3-native12-480-vlog",
             "h3-singularity-native-480-vlog", "h3-singularity-native-672-vlog", "h3-w6-native-480-vlog"]:
    path = OUTPUT / (name + ".mp4")
    if not path.is_file():
        continue
    segments, info = model.transcribe(str(path), beam_size=5, condition_on_previous_text=False,
                                      vad_filter=False)
    row = dict(case=name, detected_language=info.language, probability=info.language_probability,
               text=" ".join(segment.text.strip() for segment in segments))
    results.append(row)
    print(json.dumps(row, ensure_ascii=True), flush=True)
(OUTPUT / "speech-diagnostic.json").write_text(json.dumps(results, indent=2), encoding="utf8")
