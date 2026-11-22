"""Opt-in localhost check. Pad a small, playable MP4 without a second large input file."""
import argparse
import http.client
import json
from pathlib import Path
import struct
import time

import httpx


def run(fixture, size):
    with httpx.Client(base_url="http://127.0.0.1:8080", timeout=120) as api:
        source = fixture.read_bytes()
        assert len(source) < 8*1024**2 and size >= len(source)+16
        state = api.get("/llamacpp/media-state").raise_for_status().json()
        assert not state["busy"] and not api.get("/api/tasks").raise_for_status().json()["tasks"]
        key = "/api/v1/video-edit"
        start = time.monotonic()
        media, job = None, None
        conn = http.client.HTTPConnection("127.0.0.1", 8080, timeout=300)
        try:
            conn.putrequest("POST", key+"/media")
            conn.putheader("X-Studio-Filename","studio-size-test.mp4")
            conn.putheader("Content-Type","application/octet-stream")
            conn.putheader("Content-Length",str(size))
            conn.endheaders()
            conn.send(source)
            padding=size-len(source)
            conn.send(struct.pack(">I4sQ",1,b"free",padding))
            remaining=padding-16
            chunk=memoryview(bytes(1024**2))
            while remaining:
                block=chunk[:min(len(chunk),remaining)]
                conn.send(block)
                remaining-=len(block)
            response=conn.getresponse()
            body=response.read()
            assert response.status==200,(response.status,body[:200])
            media=json.loads(body)
            uploaded=time.monotonic()
            job=api.post(key+"/exports",json={"format":"mp3","bitrate":192,"clips":[{
                "asset":media["id"],"start":.2,"end":1.2,"audioOnly":True}]}).raise_for_status().json()["id"]
            for _ in range(300):
                status=api.get(key+"/exports/"+job).raise_for_status().json()["status"]
                if status not in ("queued","exporting"): break
                time.sleep(.1)
            assert status=="done",status
            audio=api.get(key+"/exports/"+job+"/mp3").raise_for_status().content
            assert 20000<len(audio)<35000
            print(f"{size} bytes imported in {uploaded-start:.2f}s; one second of MP3 exported in {time.monotonic()-uploaded:.2f}s ({len(audio)} bytes)")
        finally:
            conn.close()
            if media:
                api.post(key+"/discard",json={"media":[media["id"]],"exports":[job] if job else []}).raise_for_status()
                api.delete("/api/v1/files/"+media["fileId"]).raise_for_status()


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("fixture",type=Path)
    parser.add_argument("--gib",type=int,required=True,choices=range(1,33))
    args=parser.parse_args()
    run(args.fixture,args.gib*1024**3)
