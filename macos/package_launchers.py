"""Produce a transport archive with executable macOS permissions, even from Windows."""

from pathlib import Path
import zipfile


def package(destination=None):
    root = Path(__file__).resolve().parent
    target = Path(destination) if destination else root / "Inicializadores-macOS.zip"
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(root.rglob("*")):
            relative = path.relative_to(root)
            if (
                path.is_dir()
                or any(part in (".runtime", "__pycache__") for part in relative.parts)
                or path.suffix == ".zip"
            ):
                continue
            entry = zipfile.ZipInfo("macos/" + relative.as_posix())
            entry.create_system = 3
            executable = path.suffix in (".command", ".sh") or path.name in ("NeveLaunch", "applet")
            entry.external_attr = (0o100755 if executable else 0o100644) << 16
            content = path.read_bytes()
            if executable and content.startswith(b"#!"):
                content = content.replace(b"\r\n", b"\n")
            archive.writestr(entry, content)
    return target


if __name__ == "__main__":
    print(package())
