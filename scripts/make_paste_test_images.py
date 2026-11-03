"""Generate deterministic, non-user images for clipboard performance tests."""
from pathlib import Path
import numpy as np
from PIL import Image

output=Path(__file__).resolve().parents[1]/'logs/paste-performance'
output.mkdir(parents=True,exist_ok=True)
for name,width,height in [('small',960,540),('large',3840,2160)]:
    rng=np.random.default_rng(42)
    image=Image.fromarray(rng.integers(0,256,(height,width,3),dtype=np.uint8))
    image.save(output/(name+'.png'))
    if name=='large':image.save(output/(name+'.jpg'),quality=95)
