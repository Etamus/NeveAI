"""Changes apply only to the isolated macOS runtime snapshot, never to source files."""

import ast
from pathlib import Path


class MacComfy(ast.NodeTransformer):
    def visit_If(self, node):
        self.generic_visit(node)
        if ast.unparse(node.test) == "os.name != 'nt'" and any(
            isinstance(child, ast.Constant)
            and isinstance(child.value, str)
            and "requer Windows" in child.value
            for child in ast.walk(node)
        ):
            node.test = ast.Constant(False)
        return node

    def visit_Constant(self, node):
        if isinstance(node.value, str):
            if node.value == "https://download.pytorch.org/whl/cu130":
                node.value = "https://pypi.org/simple"
            elif "assert torch.cuda.is_available(), 'CUDA indisponivel'" in node.value:
                node.value = node.value.replace(
                    "assert torch.cuda.is_available(), 'CUDA indisponivel'",
                    "assert torch.backends.mps.is_available(), 'MPS indisponivel neste Mac'",
                )
        return node


def adapt_snapshot(app: Path):
    for name in ("image_fast_generation.py", "image_quality_generation.py"):
        path = app / "backend/neveai/routers" / name
        tree = MacComfy().visit(ast.parse(path.read_text(encoding="utf-8-sig")))
        ast.fix_missing_locations(tree)
        path.write_text(ast.unparse(tree) + "\n", encoding="utf-8")
    # The updater must launch our installer, not the Windows VBScript.
    path = app / "backend/neveai/main.py"
    tree = ast.parse(path.read_text(encoding="utf-8-sig"))
    replacement = ast.parse("""
def launch_installer_update_page():
    import subprocess
    subprocess.Popen(['/usr/bin/open', str(BASE_DIR.parents[1] / 'Instalar Neve.app')])
""").body[0]
    found = False
    for index, node in enumerate(tree.body):
        if isinstance(node, ast.FunctionDef) and node.name == replacement.name:
            tree.body[index] = replacement
            found = True
    if not found:
        raise RuntimeError("Contrato do atualizador mudou; adaptacao interrompida.")
    release_check = ast.parse("""
def is_compatible_llamacpp_release(release):
    import platform
    arch = 'arm64' if platform.machine() == 'arm64' else 'x64'
    return not release.get('draft') and any(
        asset.get('name', '').endswith('-bin-macos-' + arch + '.tar.gz')
        for asset in release.get('assets', []))
""").body[0]
    for index, node in enumerate(tree.body):
        if isinstance(node, ast.FunctionDef) and node.name == release_check.name:
            tree.body[index] = release_check
    path.write_text(ast.unparse(tree) + "\n", encoding="utf-8")
    path = app / "backend/neveai/routers/llamacpp.py"
    tree = ast.parse(path.read_text(encoding="utf-8-sig"))
    memory = ast.parse("""
def _get_vram_info():
    import platform
    import psutil
    memory = psutil.virtual_memory()
    total, free = memory.total, memory.available
    used = total - free
    unified = platform.machine() == 'arm64'
    gpu = {'index': 0, 'name': 'Apple Silicon - memoria unificada' if unified else 'Memoria RAM (CPU)',
           'total': total, 'used': used, 'free': free,
           'total_human': _human_size(total), 'used_human': _human_size(used), 'free_human': _human_size(free)}
    return dict(gpu, available=True, source='unified-memory' if unified else 'system-memory', gpus=[gpu])
""").body[0]
    found = False
    for index, node in enumerate(tree.body):
        if isinstance(node, ast.FunctionDef) and node.name == memory.name:
            tree.body[index] = memory
            found = True
    if not found:
        raise RuntimeError(
            "Contrato de memoria do llama.cpp mudou; adaptacao interrompida."
        )
    path.write_text(ast.unparse(tree) + "\n", encoding="utf-8")
    component = app / "src/lib/components/chat/UnifiedModels.svelte"
    content = component.read_text(encoding="utf-8")
    if ">VRAM</span>" not in content:
        raise RuntimeError(
            "Contrato do indicador de memoria mudou; adaptacao interrompida."
        )
    component.write_text(
        content.replace(">VRAM</span>", ">{$i18n.t('Memory')}</span>"), encoding="utf-8"
    )
