"""
NeveAI — Abre a interface em janela de app isolada usando Chromium/Edge em
modo --app. Sem dependências externas além da stdlib do Python.
"""

import json
import os
import re
import subprocess
import threading
import time
import winreg
import ctypes
from ctypes import wintypes

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_PROFILE = os.path.join(_BASE_DIR, "logs", "browser-app")
_WINDOW_STATE_PATH = os.path.join(_PROFILE, "window-state.json")
_TASKBAR_ICON_PATH = os.path.join(_BASE_DIR, "static", "static", "faviconbar.ico")
_READY_FILE_PATH = os.environ.get("NEVE_WINDOW_READY_FILE", "").strip()
_URL = "http://localhost:8080/?neve-desktop=1"
_WINDOW_READY_TITLE = "\u200b\u200c"
_SW_HIDE = 0
_SW_SHOWNORMAL = 1
_SW_SHOWMAXIMIZED = 3
_SW_RESTORE = 9
_TARGET_TITLE = "NeveAI"
_STATE_POLL_INTERVAL = 0.2
_STATE_STABLE_SAMPLES = 3
_ICON_GUARD_INTERVAL = 0.02
_HWND_TOPMOST = -1
_HWND_NOTOPMOST = -2
_SWP_NOSIZE = 0x0001
_SWP_NOMOVE = 0x0002
_SWP_FRAMECHANGED = 0x0020
_SWP_SHOWWINDOW = 0x0040
_GWL_EXSTYLE = -20
_WS_EX_DLGMODALFRAME = 0x00000001
_WM_GETICON = 0x007F
_WM_SETICON = 0x0080
_ICON_SMALL = 0
_ICON_BIG = 1
_ICON_SMALL2 = 2
_IMAGE_ICON = 1
_LR_LOADFROMFILE = 0x0010
_LR_DEFAULTSIZE = 0x0040
_taskbar_icon = None


class _WindowPlacement(ctypes.Structure):
    _fields_ = [
        ("length", wintypes.UINT),
        ("flags", wintypes.UINT),
        ("showCmd", wintypes.UINT),
        ("ptMinPosition", wintypes.POINT),
        ("ptMaxPosition", wintypes.POINT),
        ("rcNormalPosition", wintypes.RECT),
    ]


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
_user32.SetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPCWSTR]
_user32.SetWindowTextW.restype = wintypes.BOOL
_user32.IsWindowVisible.argtypes = [wintypes.HWND]
_user32.IsWindowVisible.restype = wintypes.BOOL
_user32.IsWindow.argtypes = [wintypes.HWND]
_user32.IsWindow.restype = wintypes.BOOL
_user32.IsIconic.argtypes = [wintypes.HWND]
_user32.IsIconic.restype = wintypes.BOOL
_user32.IsZoomed.argtypes = [wintypes.HWND]
_user32.IsZoomed.restype = wintypes.BOOL
_user32.GetWindowPlacement.argtypes = [wintypes.HWND, ctypes.POINTER(_WindowPlacement)]
_user32.GetWindowPlacement.restype = wintypes.BOOL
_user32.SetWindowPlacement.argtypes = [wintypes.HWND, ctypes.POINTER(_WindowPlacement)]
_user32.SetWindowPlacement.restype = wintypes.BOOL
_user32.MonitorFromRect.argtypes = [ctypes.POINTER(wintypes.RECT), wintypes.DWORD]
_user32.MonitorFromRect.restype = wintypes.HMONITOR
_user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
_user32.ShowWindow.restype = wintypes.BOOL
_user32.SetForegroundWindow.argtypes = [wintypes.HWND]
_user32.SetForegroundWindow.restype = wintypes.BOOL
_user32.BringWindowToTop.argtypes = [wintypes.HWND]
_user32.BringWindowToTop.restype = wintypes.BOOL
_user32.SetWindowPos.argtypes = [
    wintypes.HWND,
    wintypes.HWND,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    wintypes.UINT,
]
_user32.SetWindowPos.restype = wintypes.BOOL
_get_window_long_ptr = _user32.GetWindowLongPtrW
_get_window_long_ptr.argtypes = [wintypes.HWND, ctypes.c_int]
_get_window_long_ptr.restype = ctypes.c_ssize_t
_set_window_long_ptr = _user32.SetWindowLongPtrW
_set_window_long_ptr.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
_set_window_long_ptr.restype = ctypes.c_ssize_t
_user32.SendMessageW.argtypes = [
    wintypes.HWND,
    wintypes.UINT,
    wintypes.WPARAM,
    wintypes.LPARAM,
]
_user32.SendMessageW.restype = wintypes.LPARAM
_user32.LoadImageW.argtypes = [
    wintypes.HINSTANCE,
    wintypes.LPCWSTR,
    wintypes.UINT,
    ctypes.c_int,
    ctypes.c_int,
    wintypes.UINT,
]
_user32.LoadImageW.restype = wintypes.HANDLE

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
    ctypes.windll.user32.MessageBoxW(None, message, "NeveAI", 0x10)


def _is_supported_chromium_exe(exe: str | None) -> bool:
    return bool(exe and os.path.exists(exe) and os.path.basename(exe).lower() in _CHROMIUM_EXE_NAMES)


def _exe_from_command(cmd: str) -> str | None:
    quoted = re.match(r'"([^\"]+\.exe)"', cmd, re.IGNORECASE)
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
        key = winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, rf"{prog_id}\shell\open\command")
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


def _is_app_window_title(title: str) -> bool:
    normalized = title.strip().casefold()
    app_name = _TARGET_TITLE.casefold()
    return normalized == app_name or normalized.endswith(f" • {app_name}")


def _find_app_window(process_id: int | None) -> int | None:
    found: list[int] = []

    def callback(hwnd, _):
        if not _user32.IsWindowVisible(hwnd):
            return True

        title = _window_title(hwnd)
        pid = wintypes.DWORD()
        _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))

        if process_id is not None and pid.value == process_id:
            found.append(hwnd)
            return False

        if _is_app_window_title(title):
            found.append(hwnd)
            return False

        return True

    _user32.EnumWindows(_EnumWindowsProc(callback), 0)
    return found[0] if found else None


def _load_window_state() -> dict | None:
    try:
        with open(_WINDOW_STATE_PATH, "r", encoding="utf-8") as state_file:
            state = json.load(state_file)
    except (OSError, ValueError, TypeError):
        return None

    if not isinstance(state, dict):
        return None

    rect = state.get("normal_rect")
    if not isinstance(rect, dict):
        return None

    try:
        normalized = {
            "left": int(rect["left"]),
            "top": int(rect["top"]),
            "right": int(rect["right"]),
            "bottom": int(rect["bottom"]),
        }
    except (KeyError, TypeError, ValueError):
        return None

    if normalized["right"] - normalized["left"] < 480:
        return None
    if normalized["bottom"] - normalized["top"] < 320:
        return None

    return {
        "maximized": bool(state.get("maximized", False)),
        "normal_rect": normalized,
    }


def _save_window_state(state: dict) -> None:
    temporary_path = f"{_WINDOW_STATE_PATH}.tmp"
    try:
        os.makedirs(os.path.dirname(_WINDOW_STATE_PATH), exist_ok=True)
        with open(temporary_path, "w", encoding="utf-8") as state_file:
            json.dump(state, state_file, ensure_ascii=True, separators=(",", ":"))
        os.replace(temporary_path, _WINDOW_STATE_PATH)
    except OSError:
        try:
            os.remove(temporary_path)
        except OSError:
            pass


def _get_window_placement(hwnd: int) -> _WindowPlacement | None:
    placement = _WindowPlacement()
    placement.length = ctypes.sizeof(_WindowPlacement)
    if not _user32.GetWindowPlacement(hwnd, ctypes.byref(placement)):
        return None
    return placement


def _capture_window_state(hwnd: int) -> dict | None:
    if (
        not _user32.IsWindow(hwnd)
        or not _user32.IsWindowVisible(hwnd)
        or _user32.IsIconic(hwnd)
    ):
        return None

    placement = _get_window_placement(hwnd)
    if placement is None:
        return None

    rect = placement.rcNormalPosition
    if rect.right - rect.left < 480 or rect.bottom - rect.top < 320:
        return None

    return {
        "maximized": bool(_user32.IsZoomed(hwnd) or placement.showCmd == _SW_SHOWMAXIMIZED),
        "normal_rect": {
            "left": rect.left,
            "top": rect.top,
            "right": rect.right,
            "bottom": rect.bottom,
        },
    }


def _apply_window_state(hwnd: int, state: dict | None) -> None:
    if state is None:
        _user32.ShowWindow(hwnd, _SW_SHOWNORMAL)
        return

    placement = _get_window_placement(hwnd)
    if placement is None:
        return

    saved_rect = state["normal_rect"]
    normal_rect = wintypes.RECT(
        saved_rect["left"],
        saved_rect["top"],
        saved_rect["right"],
        saved_rect["bottom"],
    )

    # Ignore geometry left entirely outside the currently connected monitors.
    if _user32.MonitorFromRect(ctypes.byref(normal_rect), 0):
        placement.rcNormalPosition = normal_rect

    placement.flags = 0
    placement.showCmd = _SW_SHOWMAXIMIZED if state["maximized"] else _SW_SHOWNORMAL
    _user32.SetWindowPlacement(hwnd, ctypes.byref(placement))
    _user32.ShowWindow(
        hwnd,
        _SW_SHOWMAXIMIZED if state["maximized"] else _SW_SHOWNORMAL,
    )


def _hide_caption_icon(hwnd: int) -> None:
    global _taskbar_icon

    extended_style = _get_window_long_ptr(hwnd, _GWL_EXSTYLE)
    if not extended_style & _WS_EX_DLGMODALFRAME:
        _set_window_long_ptr(
            hwnd,
            _GWL_EXSTYLE,
            extended_style | _WS_EX_DLGMODALFRAME,
        )
        _user32.SetWindowPos(
            hwnd,
            0,
            0,
            0,
            0,
            0,
            _SWP_NOMOVE | _SWP_NOSIZE | _SWP_FRAMECHANGED,
        )

    if _taskbar_icon is None and os.path.exists(_TASKBAR_ICON_PATH):
        _taskbar_icon = _user32.LoadImageW(
            None,
            _TASKBAR_ICON_PATH,
            _IMAGE_ICON,
            0,
            0,
            _LR_LOADFROMFILE | _LR_DEFAULTSIZE,
        )

    if _taskbar_icon:
        icon_handle = int(_taskbar_icon)
        for icon_kind in (_ICON_BIG, _ICON_SMALL, _ICON_SMALL2):
            current_icon = int(_user32.SendMessageW(hwnd, _WM_GETICON, icon_kind, 0) or 0)
            if current_icon != icon_handle:
                _user32.SendMessageW(hwnd, _WM_SETICON, icon_kind, icon_handle)


def _clear_caption_text(hwnd: int) -> None:
    if _window_title(hwnd):
        _user32.SetWindowTextW(hwnd, "")


def _guard_window_identity(hwnd: int, process_id: int | None = None) -> None:
    """Keep Chromium favicon updates from replacing the native taskbar icon."""
    while True:
        if not _user32.IsWindow(hwnd):
            hwnd = _find_app_window(process_id)
            if hwnd is None:
                return

        _hide_caption_icon(hwnd)
        _clear_caption_text(hwnd)
        time.sleep(_ICON_GUARD_INTERVAL)


def _activate_window(hwnd: int) -> None:
    flags = _SWP_NOMOVE | _SWP_NOSIZE | _SWP_SHOWWINDOW
    _user32.SetWindowPos(hwnd, _HWND_TOPMOST, 0, 0, 0, 0, flags)
    _user32.BringWindowToTop(hwnd)
    _user32.SetForegroundWindow(hwnd)
    _user32.SetWindowPos(hwnd, _HWND_NOTOPMOST, 0, 0, 0, 0, flags)


def _bring_app_to_front(
    process: subprocess.Popen | None = None,
    state: dict | None = None,
    timeout: float = 8.0,
) -> int | None:
    process_id = process.pid if process else None
    deadline = time.time() + timeout

    while time.time() < deadline:
        hwnd = _find_app_window(process_id)
        if hwnd:
            _user32.ShowWindow(hwnd, _SW_HIDE)
            settle_deadline = time.time() + 4.0
            page_ready_at: float | None = None
            while time.time() < settle_deadline and _user32.IsWindow(hwnd):
                _hide_caption_icon(hwnd)
                if _window_title(hwnd) == _WINDOW_READY_TITLE:
                    if page_ready_at is None:
                        page_ready_at = time.time()
                    elif time.time() - page_ready_at >= 0.2:
                        break
                time.sleep(0.03)

            if not _user32.IsWindow(hwnd):
                time.sleep(0.01)
                continue

            _hide_caption_icon(hwnd)
            _clear_caption_text(hwnd)
            _apply_window_state(hwnd, state)
            _activate_window(hwnd)
            return hwnd
        time.sleep(0.01)

    return None


def _remember_window_state(
    hwnd: int,
    process_id: int | None = None,
    initial_state: dict | None = None,
) -> None:
    last_saved_state = initial_state
    pending_state: dict | None = None
    stable_samples = 0
    missing_since: float | None = None

    while True:
        if not _user32.IsWindow(hwnd) or not _user32.IsWindowVisible(hwnd):
            replacement = _find_app_window(process_id)
            if replacement is None:
                if missing_since is None:
                    missing_since = time.monotonic()
                elif time.monotonic() - missing_since >= 2.0:
                    return
                time.sleep(_STATE_POLL_INTERVAL)
                continue

            hwnd = replacement
            _hide_caption_icon(hwnd)
            _clear_caption_text(hwnd)
            pending_state = None
            stable_samples = 0

        missing_since = None
        _hide_caption_icon(hwnd)
        _clear_caption_text(hwnd)
        current_state = _capture_window_state(hwnd)
        if current_state is None or current_state == last_saved_state:
            pending_state = None
            stable_samples = 0
        elif current_state == pending_state:
            stable_samples += 1
            if stable_samples >= _STATE_STABLE_SAMPLES:
                _save_window_state(current_state)
                last_saved_state = current_state
                pending_state = None
                stable_samples = 0
        else:
            pending_state = current_state
            stable_samples = 1

        time.sleep(_STATE_POLL_INTERVAL)


def main():
    browser = _find_chromium_browser()
    if not browser:
        _show_error(
            "Não foi possível encontrar Edge, Chrome, Brave ou Chromium para abrir o NeveAI "
            "em janela de app."
        )
        return

    os.makedirs(_PROFILE, exist_ok=True)
    saved_state = _load_window_state()
    process = subprocess.Popen([
        browser,
        f"--app={_URL}",
        "--window-size=1280,820",
        "--window-position=160,80",
        "--start-minimized",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-background-mode",
        "--disable-extensions",
        "--disable-features=WebAppIconInTitlebar",
        f"--user-data-dir={_PROFILE}",
    ])
    hwnd = _bring_app_to_front(process, saved_state)
    if hwnd:
        threading.Thread(
            target=_guard_window_identity,
            args=(hwnd, process.pid),
            daemon=True,
        ).start()
        if _READY_FILE_PATH:
            try:
                os.makedirs(os.path.dirname(_READY_FILE_PATH), exist_ok=True)
                with open(_READY_FILE_PATH, "w", encoding="ascii") as ready_file:
                    ready_file.write("ready")
            except OSError:
                pass
        _remember_window_state(hwnd, process.pid, saved_state)


if __name__ == "__main__":
    main()
