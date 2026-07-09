"""
Neve AI — Abre a interface em janela de app isolada usando Chromium/Edge em
modo --app. Sem dependências externas além da stdlib do Python.
"""

import os
import re
import subprocess
import time
import winreg
import ctypes
from ctypes import wintypes

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_PROFILE   = os.path.join(_BASE_DIR, "logs", "browser-app")
_URL       = "http://localhost:8080"
_SW_RESTORE = 9
_TARGET_TITLE = "Neve AI"

_user32 = ctypes.WinDLL("user32", use_last_error=True)
_EnumWindowsProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
_user32.EnumWindows.argtypes = [_EnumWindowsProc, wintypes.LPARAM]
_user32.EnumWindows.restype = wintypes.BOOL
_user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
_user32.GetWindowThreadProcessId.restype = wintypes.DWORD
_user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
_user32.GetWindowTextLengthW.restype = ctypes.c_int
_user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
_user32.GetWindowTextW.restype = ctypes.c_int
_user32.IsWindowVisible.argtypes = [wintypes.HWND]
_user32.IsWindowVisible.restype = wintypes.BOOL
_user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
_user32.ShowWindow.restype = wintypes.BOOL
_user32.SetForegroundWindow.argtypes = [wintypes.HWND]
_user32.SetForegroundWindow.restype = wintypes.BOOL

# ProgIds de navegadores NÃO-Chromium — não suportam --app isolado.
_NON_CHROMIUM = {"firefoxurl", "firefoxhtml", "iexplore"}
_CHROMIUM_EXE_NAMES = {
    "chrome.exe",
    "msedge.exe",
    "brave.exe",
    "chromium.exe",
    "vivaldi.exe",
    "opera.exe",
}


def _show_error(message: str) -> None:
    ctypes.windll.user32.MessageBoxW(None, message, "Neve AI", 0x10)


def _is_supported_chromium_exe(exe: str | None) -> bool:
    return bool(exe and os.path.exists(exe) and os.path.basename(exe).lower() in _CHROMIUM_EXE_NAMES)


def _exe_from_command(cmd: str) -> str | None:
    quoted = re.match(r'"([^"]+\.exe)"', cmd, re.IGNORECASE)
    if quoted:
        return quoted.group(1)

    unquoted = re.match(r"([A-Za-z]:\\[^\r\n]+?\.exe)(?:\s|$)", cmd, re.IGNORECASE)
    if unquoted:
        return unquoted.group(1)

    return None


def _chromium_exe_from_progid(prog_id: str) -> str | None:
    """
    Lê HKCR\\<ProgId>\\shell\\open\\command e extrai o caminho do .exe.
    Retorna None se o ProgId não for de um navegador Chromium suportado.
    """
    if prog_id.lower() in _NON_CHROMIUM:
        return None
    try:
        key = winreg.OpenKey(winreg.HKEY_CLASSES_ROOT,
                             rf"{prog_id}\shell\open\command")
        cmd, _ = winreg.QueryValueEx(key, "")
        winreg.CloseKey(key)
        exe = _exe_from_command(cmd)
        return exe if _is_supported_chromium_exe(exe) else None
    except OSError:
        pass
    return None


def _find_default_chromium_browser() -> str | None:
    """Detecta o navegador padrão do sistema e retorna o exe se for Chromium."""
    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\Shell\Associations"
            r"\UrlAssociations\http\UserChoice",
        )
        prog_id, _ = winreg.QueryValueEx(key, "ProgId")
        winreg.CloseKey(key)
        return _chromium_exe_from_progid(prog_id)
    except OSError:
        return None


def _browser_from_app_paths(exe_name: str) -> str | None:
    subkey = rf"Software\Microsoft\Windows\CurrentVersion\App Paths\{exe_name}"
    for root_key in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        try:
            key = winreg.OpenKey(root_key, subkey)
            exe, _ = winreg.QueryValueEx(key, "")
            winreg.CloseKey(key)
            if _is_supported_chromium_exe(exe):
                return exe
        except OSError:
            continue
    return None


def _common_browser_paths() -> list[str]:
    program_files = [os.environ.get("ProgramFiles"), os.environ.get("ProgramFiles(x86)")]
    local_app_data = os.environ.get("LOCALAPPDATA")
    candidates: list[str] = []

    for base in [path for path in program_files if path]:
        candidates.extend([
            os.path.join(base, "Microsoft", "Edge", "Application", "msedge.exe"),
            os.path.join(base, "Google", "Chrome", "Application", "chrome.exe"),
            os.path.join(base, "BraveSoftware", "Brave-Browser", "Application", "brave.exe"),
            os.path.join(base, "Chromium", "Application", "chromium.exe"),
        ])

    if local_app_data:
        candidates.extend([
            os.path.join(local_app_data, "Google", "Chrome", "Application", "chrome.exe"),
            os.path.join(local_app_data, "BraveSoftware", "Brave-Browser", "Application", "brave.exe"),
            os.path.join(local_app_data, "Chromium", "Application", "chromium.exe"),
        ])

    return candidates


def _find_chromium_browser() -> str | None:
    default_browser = _find_default_chromium_browser()
    if default_browser:
        return default_browser

    for exe_name in ("msedge.exe", "chrome.exe", "brave.exe", "chromium.exe"):
        browser = _browser_from_app_paths(exe_name)
        if browser:
            return browser

    for candidate in _common_browser_paths():
        if _is_supported_chromium_exe(candidate):
            return candidate

    return None


def _window_title(hwnd) -> str:
    length = _user32.GetWindowTextLengthW(hwnd)
    if length <= 0:
        return ""

    buffer = ctypes.create_unicode_buffer(length + 1)
    _user32.GetWindowTextW(hwnd, buffer, length + 1)
    return buffer.value


def _find_app_window(process_id: int | None) -> int | None:
    found: list[int] = []

    def callback(hwnd, _):
        if not _user32.IsWindowVisible(hwnd):
            return True

        title = _window_title(hwnd)
        title_lower = title.lower()

        pid = wintypes.DWORD()
        _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))

        if process_id is not None and pid.value == process_id:
            found.append(hwnd)
            return False

        if _TARGET_TITLE.lower() in title_lower and "backend" not in title_lower:
            found.append(hwnd)
            return False

        return True

    _user32.EnumWindows(_EnumWindowsProc(callback), 0)
    return found[0] if found else None


def _bring_app_to_front(process: subprocess.Popen | None = None, timeout: float = 8.0) -> None:
    process_id = process.pid if process else None
    deadline = time.time() + timeout

    while time.time() < deadline:
        hwnd = _find_app_window(process_id)
        if hwnd:
            _user32.ShowWindow(hwnd, _SW_RESTORE)
            _user32.SetForegroundWindow(hwnd)
            return
        time.sleep(0.15)


def main():
    browser = _find_chromium_browser()
    if not browser:
        _show_error(
            "Não foi possível encontrar Edge, Chrome, Brave ou Chromium para abrir o Neve AI "
            "em janela de app."
        )
        return

    os.makedirs(_PROFILE, exist_ok=True)
    process = subprocess.Popen([
        browser,
        f"--app={_URL}",
        "--window-size=1280,820",
        "--window-position=160,80",
        "--start-windowed",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-extensions",
        f"--user-data-dir={_PROFILE}",
    ])
    _bring_app_to_front(process)


if __name__ == "__main__":
    main()
