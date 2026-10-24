"""Generate a local inspection gallery and CSV from actual benchmark artifacts."""
import csv
import html
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "logs/moss-study-20261024"
rows = [row for row in json.loads((OUTPUT / "measurements.json").read_text()) if row.get("ok")]
with (OUTPUT / "measurements.csv").open("w", newline="", encoding="utf-8") as target:
    writer = csv.writer(target)
    writer.writerow(["case", "seconds", "width", "height", "peak_C", "peak_VRAM_MiB", "average_GPU_W"])
    for row in rows:
        writer.writerow([row["key"], row["seconds"], *row["dimensions"], row["temperature_peak_c"], row["vram_peak_mib"], row["gpu_average_w"]])
figures = ['<figure><a href="../image2-modes/main.png"><img src="../image2-modes/main.png"></a><figcaption>Original</figcaption></figure>',
           '<figure><a href="../image2-modes/reference.png"><img src="../image2-modes/reference.png"></a><figcaption>Referencia de roupa</figcaption></figure>']
for row in rows:
    name = html.escape(row["key"])
    figures.append(f'<figure><a href="{name}.png"><img loading="lazy" src="{name}.png"></a><figcaption>{name}<br>{row["seconds"]:.2f} s | {row["dimensions"][0]} x {row["dimensions"][1]} | {row["temperature_peak_c"]} C</figcaption></figure>')
document = '''<!doctype html><html lang="pt-BR"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Comparacao Neve Image 3</title>
<style>body{margin:24px;font:14px system-ui;background:#161616;color:#eee}h1{font-size:22px}main{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:24px}figure{margin:0;min-width:0}img{display:block;width:100%;height:360px;object-fit:contain;background:#222;border-radius:6px}figcaption{margin-top:8px;overflow-wrap:anywhere;color:#bbb}a{color:inherit}</style>
<h1>Comparacao Neve Image 3 - 24/10/2026</h1><p>cold = processo novo; demais = servidor de benchmark aquecido. Os tempos nao incluem download. Resultados dos modelos Qwen usam seus presets atuais.</p><main>'''
(OUTPUT / "galeria.html").write_text(document + "".join(figures) + "</main></html>", encoding="utf-8")
print(f"{len(rows)} successful measured generations; gallery and CSV written")
