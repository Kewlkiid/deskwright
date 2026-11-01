"""App launching and window focus through the OS. Best-effort outside macOS."""
from __future__ import annotations

import shutil
import subprocess
import sys

PLATFORM = sys.platform


def _osascript(script: str, timeout: float = 3.0) -> str:
    out = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=timeout)
    return out.stdout.strip()


def active_window() -> dict:
    """Return {"app": ..., "title": ...} for the frontmost window."""
    try:
        if PLATFORM == "darwin":
            app = _osascript(
                'tell application "System Events" to get name of first application process whose frontmost is true'
            )
            title = ""
            try:
                title = _osascript(
                    'tell application "System Events" to tell (first application process whose frontmost is true) '
                    "to get name of front window"
                )
            except Exception:
                pass
            return {"app": app, "title": title}
        if PLATFORM.startswith("win"):
            import ctypes

            user32 = ctypes.windll.user32
            hwnd = user32.GetForegroundWindow()
            length = user32.GetWindowTextLengthW(hwnd)
            buf = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buf, length + 1)
            return {"app": "", "title": buf.value}
        if shutil.which("xdotool"):
            title = subprocess.run(
                ["xdotool", "getactivewindow", "getwindowname"], capture_output=True, text=True, timeout=2
            ).stdout.strip()
            return {"app": "", "title": title}
    except Exception:
        pass
    return {"app": "", "title": ""}


def app_window_bounds(app: str) -> tuple[float, float, float, float] | None:
    """Logical (x, y, w, h) of the app's frontmost normal window, or None (not running, hidden, or not macOS)."""
    if PLATFORM != "darwin" or not app:
        return None
    try:
        import Quartz

        opts = Quartz.kCGWindowListOptionOnScreenOnly | Quartz.kCGWindowListExcludeDesktopElements
        want = app.lower()
        for w in Quartz.CGWindowListCopyWindowInfo(opts, Quartz.kCGNullWindowID) or []:  # front to back
            owner = str(w.get("kCGWindowOwnerName", "")).lower()
            if w.get("kCGWindowLayer", 1) != 0 or not owner or (want not in owner and owner not in want):
                continue
            b = w.get("kCGWindowBounds") or {}
            if b.get("Width", 0) > 120 and b.get("Height", 0) > 120 and w.get("kCGWindowAlpha", 1) > 0:
                return float(b["X"]), float(b["Y"]), float(b["Width"]), float(b["Height"])
    except Exception:
        return None
    return None


def window_key() -> str:
    """Stable-ish identifier for the current app/window, used to key the position cache."""
    w = active_window()
    return f"{w.get('app', '')}|{w.get('title', '')}".strip("|")


def open_app(name: str) -> None:
    if PLATFORM == "darwin":
        res = subprocess.run(["open", "-a", name], capture_output=True, text=True, timeout=10)
        if res.returncode != 0:
            raise RuntimeError(res.stderr.strip() or f"Could not open {name}")
    elif PLATFORM.startswith("win"):
        subprocess.Popen(["cmd", "/c", "start", "", name], shell=False)
    else:
        launcher = shutil.which("gtk-launch") or shutil.which("xdg-open")
        if not launcher:
            raise RuntimeError("No app launcher found")
        subprocess.Popen([launcher, name])


def focus_window(title: str) -> bool:
    """Bring a window whose app name or title contains `title` to the front."""
    if PLATFORM == "darwin":
        safe = title.replace('"', '\\"')
        script = f'''
        tell application "System Events"
            repeat with p in (every application process whose background only is false)
                if name of p contains "{safe}" then
                    set frontmost of p to true
                    return "ok"
                end if
                repeat with w in (every window of p)
                    if name of w contains "{safe}" then
                        set frontmost of p to true
                        perform action "AXRaise" of w
                        return "ok"
                    end if
                end repeat
            end repeat
        end tell
        return "missing"'''
        try:
            return _osascript(script, timeout=5) == "ok"
        except Exception:
            return False
    if shutil.which("wmctrl"):
        return subprocess.run(["wmctrl", "-a", title], timeout=3).returncode == 0
    return False
