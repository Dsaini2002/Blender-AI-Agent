"""HTTPS requests that do not depend on Python's global SSL default.

Other Blender add-ons sometimes replace ``ssl._create_default_https_context`` with one that
loads a certificate file that is later missing. ``urllib.request.urlopen`` then fails with a
bare ``FileNotFoundError: [Errno 2] No such file or directory`` before any request is made.
These helpers build their own context (system certificates, plus certifi when present) and
retry once that way if the default one is broken.
"""

import ssl
import urllib.request
from typing import Optional

_CONTEXT: Optional[ssl.SSLContext] = None


def https_context() -> Optional[ssl.SSLContext]:
    global _CONTEXT
    if _CONTEXT is None:
        try:
            context = ssl.create_default_context()
        except Exception:  # noqa: BLE001
            return None
        try:
            import certifi  # type: ignore
            context.load_verify_locations(certifi.where())
        except Exception:  # noqa: BLE001 — certifi is optional
            pass
        _CONTEXT = context
    return _CONTEXT


def urlopen(request, timeout: float):
    """urllib.request.urlopen with our own SSL context - and Stop ends the wait for the AI at once (the answer, if it
    still comes, is thrown away)."""
    try:
        from .copilot import activity
    except Exception:  # noqa: BLE001
        activity = None
    if activity is None or not (activity._active.is_set() or activity._abandon.is_set()):
        return _urlopen(request, timeout)
    if activity.should_stop():
        raise RuntimeError("Stopped by user.")
    import threading
    box = {}
    done = threading.Event()

    def work():
        try:
            box["value"] = _urlopen(request, timeout)
        except BaseException as exc:  # noqa: BLE001
            box["error"] = exc
        finally:
            done.set()
    threading.Thread(target=work, name="AIAgentHTTP", daemon=True).start()
    while not done.wait(0.2):
        if activity.should_stop():
            raise RuntimeError("Stopped by user while waiting for the AI.")
    if "error" in box:
        raise box["error"]
    return box["value"]


def _urlopen(request, timeout: float):
    context = https_context()
    try:
        return urllib.request.urlopen(request, timeout=timeout, context=context)
    except (FileNotFoundError, ssl.SSLError):
        if context is None:
            raise
        # our context failed (should not happen) - try Python's default once
        return urllib.request.urlopen(request, timeout=timeout)
