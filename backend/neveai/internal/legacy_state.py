"""Import older local state without changing the active NeveAI data format."""

from pathlib import Path


def import_database(directory: Path):
    destination = directory / "neve.db"
    if destination.exists():
        return
    for name in ("ollama.db", "webui.db"):
        source = directory / name
        if source.exists():
            source.rename(destination)
            return


def import_secret(directory: Path):
    destination = directory / ".neve_secret_key"
    source = directory / ".webui_secret_key"
    if source.exists() and not destination.exists():
        try:
            source.rename(destination)
        except OSError:
            pass


def import_config_namespace(document: dict) -> bool:
    old = document.get("webui")
    if not isinstance(old, dict) or "url" not in old:
        return False
    current = document.setdefault("neve", {})
    current.setdefault("url", old["url"])
    del old["url"]
    if not old:
        del document["webui"]
    return True


LEGACY_SESSION_COOKIE = "owui-session"
