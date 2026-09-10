import csv
import io
import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from neveai.env import BASE_DIR


OFFICECLI_FORMATS = {"docx", "xlsx", "pptx"}
OFFICECLI_TIMEOUT_SECONDS = 180


class OfficeCLIError(RuntimeError):
    pass


def _officecli_binary() -> Path:
    configured = os.getenv("OFFICECLI_BIN", "").strip()
    executable = "officecli.exe" if os.name == "nt" else "officecli"
    candidates = [
        Path(configured) if configured else None,
        BASE_DIR / "node_modules" / "@officecli" / "officecli" / "vendor" / executable,
    ]
    command = shutil.which("officecli")
    if command:
        candidates.append(Path(command))
    for candidate in candidates:
        if candidate and candidate.is_file():
            return candidate
    raise OfficeCLIError("OfficeCLI is not installed")


def _run_officecli(binary: Path, *arguments: str) -> dict:
    environment = os.environ.copy()
    environment.update(
        {
            "OFFICECLI_NO_AUTO_RESIDENT": "1",
            "OFFICECLI_SKIP_UPDATE": "1",
        }
    )
    creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    try:
        process = subprocess.run(
            [str(binary), *map(str, arguments)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=OFFICECLI_TIMEOUT_SECONDS,
            check=False,
            env=environment,
            creationflags=creationflags,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise OfficeCLIError(f"OfficeCLI could not run: {error}") from error

    output = process.stdout.strip()
    try:
        payload = json.loads(output) if output else {}
    except json.JSONDecodeError:
        payload = {}
    if process.returncode != 0 or payload.get("success") is False:
        details = payload.get("error") or payload.get("message") or process.stderr.strip()
        raise OfficeCLIError(details or f"OfficeCLI exited with code {process.returncode}")
    return payload


def _strip_inline_markdown(text: str) -> str:
    text = re.sub(r"!\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1 (\2)", text)
    text = re.sub(r"(`{1,3}|\*\*|__|~~)(.*?)(\1)", r"\2", text)
    return text.replace("\\|", "|").strip()


def _markdown_table(lines: list[str], start: int) -> tuple[list[list[str]], int] | None:
    if start + 1 >= len(lines) or "|" not in lines[start]:
        return None
    separator = lines[start + 1].strip().strip("|")
    if not separator or not all(
        re.fullmatch(r":?-{3,}:?", cell.strip()) for cell in separator.split("|")
    ):
        return None
    rows = []
    index = start
    while index < len(lines) and "|" in lines[index] and lines[index].strip():
        if index != start + 1:
            rows.append(
                [
                    _strip_inline_markdown(cell.strip())
                    for cell in lines[index].strip().strip("|").split("|")
                ]
            )
        index += 1
    return rows, index


def _docx_commands(content: str) -> list[dict]:
    commands: list[dict] = [
        {
            "command": "set",
            "path": "/",
            "props": {"docDefaults.font": "Arial", "docDefaults.fontSize": "11pt"},
        }
    ]
    lines = content.splitlines()
    index = 0
    in_code = False
    table_index = 0
    while index < len(lines):
        line = lines[index]
        stripped = line.strip()
        if stripped.startswith("```"):
            in_code = not in_code
            index += 1
            continue

        table_data = None if in_code else _markdown_table(lines, index)
        if table_data:
            rows, index = table_data
            if rows:
                table_index += 1
                width = max(len(row) for row in rows)
                commands.append(
                    {
                        "command": "add",
                        "parent": "/body",
                        "type": "table",
                        "props": {"rows": str(len(rows)), "cols": str(width)},
                    }
                )
                for row_index, row in enumerate(rows, start=1):
                    for column_index, value in enumerate(row, start=1):
                        props = {"text": str(value)}
                        if row_index == 1:
                            props.update({"bold": "true", "shading": "E8EEF7"})
                        commands.append(
                            {
                                "command": "set",
                                "path": (
                                    f"/body/tbl[{table_index}]/tr[{row_index}]"
                                    f"/tc[{column_index}]"
                                ),
                                "props": props,
                            }
                        )
            continue

        props: dict[str, str] = {"text": ""}
        if not stripped:
            pass
        elif in_code:
            props = {"text": line, "font": "Consolas", "size": "9pt"}
        elif match := re.match(r"^(#{1,6})\s+(.+)$", stripped):
            level = len(match.group(1))
            props = {
                "text": _strip_inline_markdown(match.group(2)),
                "bold": "true",
                "size": f"{max(12, 22 - level * 2)}pt",
                "color": "1F2937",
                "spaceBefore": "8pt",
                "spaceAfter": "4pt",
            }
        elif re.match(r"^[-*+]\s+", stripped):
            props = {
                "text": "- " + _strip_inline_markdown(re.sub(r"^[-*+]\s+", "", stripped)),
                "left": "18pt",
            }
        elif re.match(r"^\d+[.)]\s+", stripped):
            props = {"text": _strip_inline_markdown(stripped)}
        else:
            props = {"text": _strip_inline_markdown(line)}
        commands.append(
            {"command": "add", "parent": "/body", "type": "paragraph", "props": props}
        )
        index += 1
    return commands


def _normalize_sheet_rows(value: Any) -> list[list[Any]]:
    if isinstance(value, dict):
        value = value.get("rows", value.get("data", []))
    if not isinstance(value, list):
        raise OfficeCLIError("Each spreadsheet must provide a rows list")
    if value and all(isinstance(row, dict) for row in value):
        headers = list(dict.fromkeys(key for row in value for key in row.keys()))
        return [headers, *[[row.get(header, "") for header in headers] for row in value]]
    return [row if isinstance(row, list) else [row] for row in value]


def _excel_column(index: int) -> str:
    result = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        result = chr(65 + remainder) + result
    return result


def _safe_sheet_name(value: Any, index: int, used: set[str]) -> str:
    base = re.sub(r"[\\/*?:\[\]]", "_", str(value or f"Planilha {index}"))[:31]
    base = base.strip(" '") or f"Planilha {index}"
    name = base
    suffix = 2
    while name.casefold() in used:
        name = f"{base[:27]} {suffix}"
        suffix += 1
    used.add(name.casefold())
    return name


def _xlsx_commands(content: str) -> list[dict]:
    try:
        payload = json.loads(content)
    except json.JSONDecodeError:
        payload = {
            "sheets": [
                {"name": "Planilha", "rows": list(csv.reader(io.StringIO(content)))}
            ]
        }
    sheets = payload.get("sheets", []) if isinstance(payload, dict) else payload
    if not isinstance(sheets, list) or not sheets:
        sheets = [{"name": "Planilha", "rows": []}]

    commands: list[dict] = []
    used: set[str] = set()
    for sheet_index, raw_sheet in enumerate(sheets[:50], start=1):
        sheet = raw_sheet if isinstance(raw_sheet, dict) else {"rows": raw_sheet}
        name = _safe_sheet_name(sheet.get("name"), sheet_index, used)
        if sheet_index == 1:
            commands.append({"command": "set", "path": "/Sheet1", "props": {"name": name}})
        else:
            commands.append(
                {"command": "add", "parent": "/", "type": "sheet", "props": {"name": name}}
            )
        rows = _normalize_sheet_rows(sheet)
        for row_index, row in enumerate(rows, start=1):
            for column_index, value in enumerate(row, start=1):
                props: dict[str, Any] = {"value": "" if value is None else value}
                if row_index == 1:
                    props.update({"bold": "true", "fill": "DCE6F1"})
                commands.append(
                    {
                        "command": "set",
                        "path": f"/{name}/{_excel_column(column_index)}{row_index}",
                        "props": props,
                    }
                )
    return commands


def _pptx_commands(content: str) -> list[dict]:
    try:
        payload = json.loads(content)
    except json.JSONDecodeError:
        payload = {
            "slides": [
                {"title": "", "content": section.strip()}
                for section in re.split(r"\n\s*---\s*\n", content)
                if section.strip()
            ]
        }
    slides = payload.get("slides", []) if isinstance(payload, dict) else payload
    if not isinstance(slides, list):
        raise OfficeCLIError("The presentation must provide a slides list")
    if not slides:
        slides = [{"title": "", "content": []}]

    commands: list[dict] = []
    for slide_index, raw_slide in enumerate(slides[:100], start=1):
        slide = raw_slide if isinstance(raw_slide, dict) else {"content": raw_slide}
        title = _strip_inline_markdown(str(slide.get("title") or ""))
        commands.append(
            {
                "command": "add",
                "parent": "/",
                "type": "slide",
                "props": {"title": title, "background": "F7F9FC"},
            }
        )
        content_value = slide.get("content", slide.get("bullets", []))
        items = (
            content_value
            if isinstance(content_value, list)
            else str(content_value).splitlines()
        )
        body = "\n".join(
            f"- {_strip_inline_markdown(str(item))}" for item in items if str(item).strip()
        )
        if body:
            commands.append(
                {
                    "command": "add",
                    "parent": f"/slide[{slide_index}]",
                    "type": "shape",
                    "props": {
                        "text": body,
                        "x": "1.5cm",
                        "y": "4cm",
                        "w": "22cm",
                        "h": "10cm",
                        "font": "Arial",
                        "size": "22pt",
                        "color": "263244",
                        "fill": "FFFFFF",
                        "line.color": "D9E2EC",
                    },
                }
            )
    return commands


def build_officecli_file(filename: str, content: str, file_format: str) -> bytes:
    normalized_format = file_format.lower().lstrip(".")
    if normalized_format not in OFFICECLI_FORMATS:
        raise OfficeCLIError(f"Unsupported OfficeCLI format: {file_format}")
    binary = _officecli_binary()
    builders = {
        "docx": _docx_commands,
        "xlsx": _xlsx_commands,
        "pptx": _pptx_commands,
    }
    commands = builders[normalized_format](content)

    with tempfile.TemporaryDirectory(prefix="neveai-officecli-") as directory:
        output_path = Path(directory) / Path(filename).name
        commands_path = Path(directory) / "commands.json"
        commands_path.write_text(json.dumps(commands, ensure_ascii=False), encoding="utf-8")
        _run_officecli(binary, "create", str(output_path), "--json")
        _run_officecli(
            binary,
            "batch",
            str(output_path),
            "--input",
            str(commands_path),
            "--json",
        )
        _run_officecli(binary, "validate", str(output_path), "--json")
        if not output_path.is_file() or output_path.stat().st_size == 0:
            raise OfficeCLIError("OfficeCLI did not create the requested file")
        return output_path.read_bytes()
