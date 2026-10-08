#!/bin/bash
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd -P)"
cd "$HERE"
if [ "$(uname -s)" != Darwin ]; then
    printf 'Este inicializador e exclusivo do macOS. O Windows nao foi alterado.\n' >&2
    exit 1
fi
ARCH="$(uname -m)"
if [ "$(sysctl -in sysctl.proc_translated 2>/dev/null || true)" = 1 ]; then
    printf 'Abra o Terminal sem Rosetta para instalar o ambiente ARM64 nativo.\n' >&2
    exit 1
fi
case "$ARCH" in
    arm64) UV_ARCH=aarch64 ;;
    x86_64) UV_ARCH=x86_64 ;;
    *) printf 'Arquitetura nao suportada: %s\n' "$ARCH" >&2; exit 1 ;;
esac
if [ "$(sw_vers -productVersion | cut -d. -f1)" -lt 14 ]; then
    printf 'Esta distribuicao requer macOS 14 ou posterior.\n' >&2
    exit 1
fi
export UV_CACHE_DIR="$HERE/.runtime/cache/uv"
export UV_PYTHON_INSTALL_DIR="$HERE/.runtime/python"
export UV_TOOL_DIR="$HERE/.runtime/tools/uv-tools"
export HF_HOME="$HERE/.runtime/cache/huggingface"
export XDG_CACHE_HOME="$HERE/.runtime/cache"
export PYTHONNOUSERSITE=1
export PYTHONDONTWRITEBYTECODE=1
export PIP_CACHE_DIR="$HERE/.runtime/cache/pip"
export npm_config_cache="$HERE/.runtime/cache/npm"
export TMPDIR="$HERE/.runtime/tmp"
UV="$HERE/.runtime/tools/uv/uv"
PY="$HERE/.runtime/venv/bin/python"
MODE="${1:-doctor}"
shift || true
mkdir -p "$HERE/.runtime/logs" "$TMPDIR"
if [ "$MODE" = install ]; then
    if [ ! -x "$UV" ]; then
        printf '[1/4] Baixando UV nativo e verificando checksum...\n'
        UV_VERSION=0.12.23
        ASSET="uv-$UV_ARCH-apple-darwin.tar.gz"
        STAGE="$(mktemp -d "$HERE/.runtime/uv-stage.XXXXXX")"
        trap 'rm -rf "$STAGE"' EXIT
        BASE="https://github.com/astral-sh/uv/releases/download/$UV_VERSION"
        curl --proto '=https' --tlsv1.2 --connect-timeout 20 --max-time 300 -fL --retry 3 "$BASE/$ASSET" -o "$STAGE/$ASSET"
        curl --proto '=https' --tlsv1.2 --connect-timeout 20 --max-time 60 -fL --retry 3 "$BASE/$ASSET.sha256" -o "$STAGE/checksum"
        EXPECTED="$(awk '{print $1}' "$STAGE/checksum")"
        ACTUAL="$(shasum -a 256 "$STAGE/$ASSET" | awk '{print $1}')"
        if [ "$EXPECTED" != "$ACTUAL" ]; then printf 'Checksum UV incorreto.\n' >&2; exit 1; fi
        tar -xzf "$STAGE/$ASSET" -C "$STAGE"
        mkdir -p "$(dirname "$UV")"
        cp "$STAGE/uv-$UV_ARCH-apple-darwin/uv" "$UV"
        chmod 755 "$UV"
    fi
    printf '[2/4] Preparando Python 3.11 nativo...\n'
    "$UV" python install 3.11
    if [ ! -x "$PY" ]; then "$UV" venv "$HERE/.runtime/venv" --python 3.11; fi
    printf '[3/4] Preparando a janela Cocoa...\n'
    "$UV" pip install --python "$PY" 'pywebview>=5,<7' pyobjc-framework-Cocoa pyobjc-framework-WebKit packaging
    printf '[4/4] Abrindo instalador...\n'
fi
if [ ! -x "$PY" ]; then
    printf 'Execute instalar.command primeiro.\n' >&2
    exit 1
fi
exec "$PY" "$HERE/manage.py" "$MODE" "$@"
