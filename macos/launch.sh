#!/bin/bash
# Shared Finder/Terminal entry point: errors must not disappear with the process.
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd -P)"
MODE="${1:-doctor}"
shift || true
case "$MODE" in install|start|doctor) ;; *) printf 'Modo invalido.\n' >&2; exit 2 ;; esac
if [ "$(uname -s)" != Darwin ]; then
    printf 'Este inicializador e exclusivo do macOS.\n' >&2
    exit 1
fi
if ! mkdir -p "$HERE/.runtime/logs"; then
    printf 'Nao foi possivel gravar nesta pasta. Mova o projeto para uma pasta do seu usuario.\n' >&2
    if [ -x /usr/bin/osascript ] && [ "${NEVE_MACOS_NO_ALERT:-0}" != 1 ]; then
        /usr/bin/osascript -e 'display alert "Pasta sem permissao de escrita" message "Mova o projeto Neve para uma pasta do seu usuario antes de instalar." as critical' || true
    fi
    exit 1
fi
LOG="$HERE/.runtime/logs/bootstrap-$MODE.log"
printf '\n=== Neve macOS: %s - %s ===\nPasta: %s\n' "$MODE" "$(date)" "$HERE" >>"$LOG"
if [ "${NEVE_MACOS_NO_TERMINAL:-0}" = 1 ]; then
    if [ -x /usr/bin/osascript ] && [ "${NEVE_MACOS_NO_ALERT:-0}" != 1 ]; then
        /usr/bin/osascript -e 'display notification "Preparando o ambiente. A janela abrira apos a preparacao." with title "Neve macOS"' >/dev/null 2>&1 || true
    fi
    /bin/bash "$HERE/bootstrap.sh" "$MODE" "$@" >>"$LOG" 2>&1
    RESULT=$?
else
    printf 'Neve macOS: preparando ambiente...\nA janela abrira depois da preparacao.\nLog: %s\n\n' "$LOG"
    /bin/bash "$HERE/bootstrap.sh" "$MODE" "$@" 2>&1 | /usr/bin/tee -a "$LOG"
    RESULT=${PIPESTATUS[0]}
fi
if [ "$RESULT" -ne 0 ]; then
    printf '\nA Neve nao iniciou (codigo %s).\nLog: %s\n' "$RESULT" "$LOG" >&2
    if [ -x /usr/bin/osascript ] && [ "${NEVE_MACOS_NO_ALERT:-0}" != 1 ]; then
        DETAIL="$(tail -n 12 "$LOG")"
        /usr/bin/osascript - "$LOG" "$DETAIL" <<'APPLESCRIPT' || true
on run arguments
    set logPath to item 1 of arguments
    set details to item 2 of arguments
    set answer to display alert "Nao foi possivel abrir a Neve" message details buttons {"Abrir log", "OK"} default button "Abrir log" as critical
    if button returned of answer is "Abrir log" then
        do shell script "/usr/bin/open -a TextEdit " & quoted form of logPath
    end if
end run
APPLESCRIPT
    fi
    if [ -t 0 ] && [ "${NEVE_MACOS_NO_TERMINAL:-0}" != 1 ]; then
        read -r -p 'Pressione Enter para fechar depois de ler o erro. ' _ || true
    fi
fi
exit "$RESULT"
