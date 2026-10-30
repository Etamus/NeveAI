"""Run one owned benchmark with thermal telemetry and guaranteed power restoration."""
import argparse
import json
import subprocess
import time
from pathlib import Path

import psutil

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "logs/runtime-upgrade-20261029"


def smi(*args):
    return subprocess.check_output(["nvidia-smi", *args], text=True, timeout=10, creationflags=0x08000000).strip()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--name", required=True)
    parser.add_argument("--timeout", type=int, default=900)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    original = float(smi("--query-gpu=power.limit", "--format=csv,noheader,nounits"))
    samples = []
    process = None
    start = time.monotonic()
    reason = None
    try:
        smi("-pl", str(min(original, 250)))
        with (REPORT / (args.name + ".log")).open("wb") as output:
            process = subprocess.Popen(command, cwd=ROOT, stdout=output, stderr=subprocess.STDOUT, creationflags=0x08000000)
            while process.poll() is None:
                temperature, memory, watts = map(float, smi("--query-gpu=temperature.gpu,memory.used,power.draw", "--format=csv,noheader,nounits").split(","))
                samples.append(dict(seconds=time.monotonic()-start, temperature_c=temperature, vram_mib=memory, power_w=watts, ram_used_gib=psutil.virtual_memory().used/1024**3))
                if temperature >= 76 or time.monotonic()-start > args.timeout:
                    reason = "thermal ceiling" if temperature >= 76 else "timeout"
                    raise RuntimeError(reason)
                time.sleep(0.5)
            if process.returncode:
                raise RuntimeError(f"Benchmark failed: {process.returncode}")
    finally:
        if process is not None and process.poll() is None:
            parent = psutil.Process(process.pid)
            children = parent.children(recursive=True)
            for child in reversed(children):
                try:
                    child.kill()
                except psutil.NoSuchProcess:
                    pass
            process.kill()
            process.wait()
        smi("-pl", str(original))
        (REPORT / (args.name + "-telemetry.json")).write_text(json.dumps(dict(samples=samples, reason=reason, exit_code=process.returncode if process else None, seconds=time.monotonic()-start), indent=2))
    print(args.name + " completed", flush=True)


if __name__ == "__main__":
    main()
