"""Real streaming, reasoning, JSON and tool-call checks on an isolated llama-server."""
import argparse
import json
import re
import socket
import subprocess
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "logs/runtime-upgrade-20261029"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--binary", required=True)
    parser.add_argument("--label", required=True)
    parser.add_argument("--model", default="Qwen3.5 9B MTP UDQ4_K_XL.gguf")
    parser.add_argument("--mandatory-reasoning", action="store_true")
    parser.add_argument("--prediction", choices=["none", "draft-mtp", "ngram-mod"], default="none")
    args = parser.parse_args()
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    model = ROOT / "models" / args.model
    binary = Path(args.binary).resolve()
    command = [str(binary), "--model", str(model), "--host", "127.0.0.1", "--port", str(port),
               "--n-gpu-layers", "99", "--ctx-size", "8192", "--flash-attn", "auto", "--cache-type-k", "q8_0",
               "--cache-type-v", "q8_0", "--parallel", "1", "--no-webui", "--context-shift"]
    if args.prediction != "none":
        command += ["--spec-type", args.prediction]
        if args.prediction == "draft-mtp":
            command += ["--spec-draft-n-max", "4"]
        else:
            command += ["--spec-ngram-mod-n-match", "16", "--spec-ngram-mod-n-min", "8", "--spec-ngram-mod-n-max", "32"]
    results = []
    with (REPORT / (args.label + "-server.log")).open("wb") as log:
        server = subprocess.Popen(command, cwd=binary.parent, stdout=log, stderr=subprocess.STDOUT, creationflags=0x08000000)
        try:
            with httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=180) as client:
                for _ in range(180):
                    if server.poll() is not None:
                        raise RuntimeError("llama-server failed to start")
                    try:
                        if client.get("/health", timeout=1).is_success:
                            break
                    except httpx.HTTPError:
                        pass
                    time.sleep(0.5)
                else:
                    raise TimeoutError("llama health timeout")
                cases = [
                    ("stream", dict(messages=[dict(role="user", content="Explain in three short sentences how rain forms.")], stream=True, chat_template_kwargs={"enable_thinking": False}, reasoning_format="none")),
                    ("reasoning", dict(messages=[dict(role="user", content="Calculate 17 times 23. Give the result.")], stream=True, thinking_budget_tokens=64, chat_template_kwargs={"enable_thinking": True}, reasoning_format="deepseek")),
                    ("continue", dict(messages=[dict(role="user", content="Write a short story."), dict(role="assistant", content="Lia opened the wooden door and saw a silver bird."), dict(role="user", content="Continue the story directly, without repeating the existing text.")], stream=True, chat_template_kwargs={"enable_thinking": True}, thinking_budget_tokens=64, reasoning_format="deepseek")),
                    ("json", dict(messages=[dict(role="user", content='Return JSON with city="Paris" and country="France".')], response_format={"type": "json_object"}, chat_template_kwargs={"enable_thinking": False}, reasoning_format="deepseek")),
                    ("tools", dict(messages=[dict(role="user", content="Call get_weather for Paris.")], tools=[dict(type="function", function=dict(name="get_weather", description="Get current weather", parameters={"type": "object", "properties": {"city": {"type": "string"}}, "required": ["city"]}))], tool_choice="required", chat_template_kwargs={"enable_thinking": False}, reasoning_format="deepseek")),
                ]
                for name, body in cases:
                    body.update(temperature=0, seed=42, max_tokens=192)
                    if args.mandatory_reasoning:
                        body.update(chat_template_kwargs={"reasoning_effort": "low"}, reasoning_effort="low",
                                    reasoning_format="deepseek", thinking_budget_tokens=64, max_tokens=384)
                    start = time.perf_counter()
                    events, content, reasoning, tools = [], "", "", []
                    if body.get("stream"):
                        with client.stream("POST", "/v1/chat/completions", json=body) as response:
                            response.raise_for_status()
                            for line in response.iter_lines():
                                if not line.startswith("data: ") or line == "data: [DONE]":
                                    continue
                                event = json.loads(line[6:])
                                events.append(event)
                                for choice in event.get("choices", []):
                                    delta = choice.get("delta", {})
                                    content += delta.get("content") or ""
                                    reasoning += delta.get("reasoning_content") or ""
                        assert content.strip(), (name, events)
                        if name in {"reasoning", "continue"}:
                            assert "<think>" not in content and "</think>" not in content, content
                            assert reasoning.strip(), (name, "No reasoning channel")
                        else:
                            assert not re.search(r"<think>\s*\S[\s\S]*?</think>", content), content
                    else:
                        response = client.post("/v1/chat/completions", json=body)
                        response.raise_for_status()
                        events = [response.json()]
                        message = events[0]["choices"][0]["message"]
                        content = message.get("content") or ""
                        tools = message.get("tool_calls") or []
                        if name == "json":
                            assert json.loads(content)["city"] == "Paris", content
                        else:
                            assert tools[0]["function"]["name"] == "get_weather", message
                            assert json.loads(tools[0]["function"]["arguments"])["city"] == "Paris", tools
                    result = dict(case=name, seconds=time.perf_counter()-start, content=content, reasoning=reasoning, tools=tools, events=events)
                    results.append(result)
                    print(json.dumps({k: result[k] for k in ("case", "seconds", "content", "reasoning", "tools")}), flush=True)
        finally:
            server.terminate()
            try:
                server.wait(15)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait()
            (REPORT / (args.label + ".json")).write_text(json.dumps(dict(command=command, results=results), indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
