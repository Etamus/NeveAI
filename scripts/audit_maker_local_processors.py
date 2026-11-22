"""Generate inspectable A/B media from the local test clip without modifying a chat."""
import base64
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace

import av
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"backend"))
from neveai.routers import video_edit as router


def main():
    out = ROOT / "logs/maker-media-click"
    out.mkdir(exist_ok=True,parents=True)
    original = out/"original.mp4"
    subprocess.run([router.ffmpeg_binary(),"-y","-v","error","-ss","15","-i",str(ROOT/"videoteste/teste.mp4"),
                    "-t","1.25","-c:v","libx264","-c:a","aac",str(original)],check=True)
    app = FastAPI()
    app.include_router(router.router)
    app.dependency_overrides[router.get_verified_user] = lambda: SimpleNamespace(id="audit")
    with tempfile.TemporaryDirectory() as temp, TestClient(app) as client:
        router.ROOT = Path(temp)
        router.TOOL_ROOT = ROOT/"backend/data/cache/video_edit_tools"
        with original.open("rb") as stream:
            asset = client.post("/media",files={"file":("scene.mp4",stream,"video/mp4")}).json()
        for op in ("erase",):
            route = "/media/"+asset["id"]+"/selection"
            first = client.post(route,json={"operation":op,"start":0,"points":[[.834,.625,1]]})
            first.raise_for_status()
            mask = first.json()["mask"].split(",")[1]
            (out/f"{op}-single-click.png").write_bytes(base64.b64decode(mask))
            response = client.post("/media/"+asset["id"]+"/process",json={"start":0,"end":1.25,
                "operation":op,"selection":mask})
            response.raise_for_status()
            result = response.json()
            (out/f"{op}.mp4").write_bytes(client.get("/media/"+result["id"]).content)
            print(op,result["fps"],result["duration"],result["audio"],flush=True)
    sheet = Image.new("RGB",(3*384,2*(216+20)))
    draw = ImageDraw.Draw(sheet)
    for row,name in enumerate(("original","erase")):
        with av.open(str(out/f"{name}.mp4")) as c:
            frames = list(c.decode(video=0))
        draw.text((4,row*236+2),name,fill="white")
        for col,frame in enumerate([frames[0],frames[len(frames)//2],frames[-1]]):
            sheet.paste(frame.to_image().resize((384,216)),(col*384,row*236+20))
    sheet.save(out/"comparison.jpg",quality=92)


if __name__ == "__main__":
    main()
