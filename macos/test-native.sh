#!/bin/bash
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd -P)"
PY="$HERE/.runtime/venv/bin/python"
if [ "$(uname -s)" != Darwin ]; then printf 'Teste nativo exige macOS.\n' >&2; exit 1; fi
"$PY" -m unittest discover -s "$HERE" -p test_macos.py -v
/bin/bash "$HERE/diagnosticar.command" --smoke
"$HERE/.runtime/app/llamacpp-server/bin/llama-server" --version
"$PY" -c 'import webview, torch; print("Cocoa importado; MPS:", torch.backends.mps.is_available())'
printf '\nTeste de inferencia: baixe/selecione um GGUF na interface e envie uma mensagem.\n'
printf 'Teste visual: abra Iniciar Neve.app; verifique chat, arquivos, imagens e musica.\n'
