"""One-time localStorage export; never reuse a browser profile as a WebView UDF."""
import asyncio
import json
from pathlib import Path
import subprocess
import time


async def export_legacy_storage(root, destination=None):
    legacy = root / "logs/browser-app"
    output = Path(destination) if destination is not None else root / "logs/webview2/local-storage-migration.json"
    marker = root / "logs/webview2/migration-complete"
    if (destination is None and marker.exists()) or output.exists():
        return
    if not (legacy / "Default/Local Storage/leveldb").is_dir():
        return
    import aiohttp
    import psutil
    names = {"brave.exe", "chrome.exe", "msedge.exe", "chromium.exe", "vivaldi.exe", "opera.exe"}
    for process in psutil.process_iter(["name", "cmdline"]):
        try:
            if (process.info["name"] or "").lower() in names and any(str(legacy).lower() in item.lower() for item in process.info["cmdline"] or []):
                raise RuntimeError("Feche a janela antiga do NeveAI antes da primeira abertura com WebView2. O perfil antigo sera preservado.")
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    last_browser = (legacy / "Last Browser").read_bytes()
    browser = Path(last_browser.decode("utf-16-le").strip("\x00\r\n "))
    if not browser.is_file() or browser.name.lower() not in names:
        raise RuntimeError("O navegador antigo nao esta disponivel para transferir as preferencias. O perfil original nao foi alterado.")
    port_file = legacy / "DevToolsActivePort"
    port_file.unlink(missing_ok=True)
    child = subprocess.Popen([str(browser), "--headless=new", "--remote-debugging-address=127.0.0.1", "--remote-debugging-port=0", "--no-first-run", "--no-default-browser-check", "--user-data-dir=" + str(legacy), "about:blank"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW)
    try:
        deadline = time.monotonic() + 30
        while not port_file.exists():
            if child.poll() is not None or time.monotonic() > deadline:
                raise RuntimeError("Nao foi possivel ler as preferencias da janela anterior.")
            await asyncio.sleep(0.1)
        port = int(port_file.read_text().splitlines()[0])
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as session:
            async with session.get(f"http://127.0.0.1:{port}/json/list") as response:
                pages = await response.json()
            endpoint = next(item["webSocketDebuggerUrl"] for item in pages if item["type"] == "page")
            async with session.ws_connect(endpoint, max_msg_size=16 * 1024 * 1024) as websocket:
                counter = 0
                async def call(method, params=None):
                    nonlocal counter
                    counter += 1
                    await websocket.send_json({"id": counter, "method": method, "params": params or {}})
                    async for packet in websocket:
                        data = json.loads(packet.data)
                        if data.get("id") == counter:
                            if "error" in data:
                                raise RuntimeError("Falha ao transferir as preferencias anteriores.")
                            return data.get("result", {})
                    raise RuntimeError("O navegador antigo encerrou a transferencia de preferencias.")
                values = {}
                for origin in ("http://127.0.0.1:8080", "http://localhost:8080"):
                    await call("Page.navigate", {"url": origin + "/health"})
                    for _ in range(100):
                        state = await call("Runtime.evaluate", {"expression": "location.origin", "returnByValue": True})
                        if state.get("result", {}).get("value") == origin:
                            break
                        await asyncio.sleep(0.05)
                    else:
                        raise RuntimeError("Servidor local indisponivel durante a transferencia de preferencias.")
                    result = await call("Runtime.evaluate", {"expression": "Object.fromEntries(Object.keys(localStorage).map(key=>[key,localStorage.getItem(key)]))", "returnByValue": True})
                    value = result.get("result", {}).get("value")
                    if not isinstance(value, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in value.items()):
                        raise RuntimeError("Formato inesperado das preferencias anteriores.")
                    values.update(value)
                output.parent.mkdir(parents=True, exist_ok=True)
                temporary = output.with_suffix(".tmp")
                temporary.write_text(json.dumps(values, ensure_ascii=True), encoding="utf-8")
                temporary.replace(output)
                await websocket.send_json({"id": counter + 1, "method": "Browser.close"})
        try:
            child.wait(timeout=10)
        except subprocess.TimeoutExpired:
            child.terminate()
    finally:
        if child.poll() is None:
            child.terminate()
            child.wait(timeout=10)
        port_file.unlink(missing_ok=True)


def migrate(root):
    asyncio.run(export_legacy_storage(Path(root)))
