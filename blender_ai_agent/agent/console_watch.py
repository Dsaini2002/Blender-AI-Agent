"""
console_watch.py
=================
Hinglish: Kaam chalte waqt Blender ke console mein jo bhi chhapta hai (Python errors, C-level warnings jaise
"QuadriFlow: mesh needs to be manifold", glTF importer ke messages) use PAKAD kar baad mein padhna.

  ConsoleCapture      with-block ke andar ka stdout/stderr alag se jama karta hai AUR user ke console par pehle jaisa dikhata bhi rehta hai
                      * fd-level (best): fd 1/2 ko pipe se jodta hai, ek thread asli console par wapas likhta rehta hai (C ke printf bhi pakde jaate hain)
                      * python-level (fallback): sys.stdout/sys.stderr ko tee se badalta hai
  analyze_console     text -> Finding list (error / warning / info), shor (blenderkit, TIMING...) hata kar, har ek ke saath hint

Kuch bhi fail ho (fd na mile, Windows GUI mode...) to chupchap agle tareeke par; kabhi exception nahi uthta.
"""

import logging
import os
import re
import sys
import threading
from dataclasses import dataclass
from typing import List, Optional


class _Tee:
    """Python-level fallback: likhna asli stream par bhi, aur buffer mein bhi."""

    def __init__(self, original, sink):
        self._original, self._sink = original, sink

    def write(self, data):
        try:
            self._sink(data if isinstance(data, str) else data.decode("utf-8", "replace"))
        except Exception:  # noqa: BLE001
            pass
        try:
            return self._original.write(data)
        except Exception:  # noqa: BLE001
            return len(data) if hasattr(data, "__len__") else 0

    def flush(self):
        try:
            self._original.flush()
        except Exception:  # noqa: BLE001
            pass

    def __getattr__(self, name):                    # isatty, fileno, encoding...
        return getattr(self._original, name)


class _ListHandler(logging.Handler):
    def __init__(self, sink):
        super().__init__(level=logging.WARNING)
        self._sink = sink

    def emit(self, record):
        try:
            self._sink(self.format(record) + "\n")
            sys.stderr.write(self.format(record) + "\n")          # lastResort ki tarah dikhta bhi rahe
        except Exception:  # noqa: BLE001
            pass


class ConsoleCapture:
    MAX_CHARS = 300_000
    # Windows par console ke sys.stdout ke print/flush fd ke bajaye seedha console handle se likhte hain; fd ko pipe se badalne par
    # "OSError: [WinError 1] Incorrect function" aata hai (asli test run mein dikha). Isliye Windows par fd-level capture BAND:
    # sirf Python-level (print / warnings / logging). C-level warnings (jaise QuadriFlow) wahan nahi pakde jaate.
    FD_SUPPORTED = os.name != "nt"

    def __init__(self, fd_level: bool = True):
        self.fd_level = fd_level
        self.mode = "none"
        self._chunks: List[str] = []
        self._size = 0
        self._lock = threading.Lock()
        self._saved: dict = {}
        self._readers: list = []
        self._originals = None
        self._handler: Optional[logging.Handler] = None
        self._active = False

    # ------------------------------------------------------------------
    def _add(self, text: str) -> None:
        with self._lock:
            if self._size < self.MAX_CHARS:
                self._chunks.append(text[: self.MAX_CHARS - self._size])
                self._size += len(text)

    def text(self) -> str:
        with self._lock:
            return "".join(self._chunks)

    # ------------------------------------------------------------------
    def _pump(self, read_fd: int, out_fd: int) -> None:
        while True:
            try:
                data = os.read(read_fd, 65536)
            except OSError:
                break
            if not data:
                break
            self._add(data.decode("utf-8", "replace"))
            try:
                os.write(out_fd, data)
            except OSError:
                pass

    @staticmethod
    def _flush_python_and_c() -> None:
        for stream in (sys.stdout, sys.stderr):
            try:
                stream.flush()
            except Exception:  # noqa: BLE001
                pass
        try:                                                        # C stdio buffer bhi (printf)
            import ctypes
            libc = ctypes.cdll.msvcrt if os.name == "nt" else ctypes.CDLL(None)
            libc.fflush(None)
        except Exception:  # noqa: BLE001
            pass

    def _start_fd(self) -> None:
        self._flush_python_and_c()
        started = []
        try:
            for fd in (1, 2):
                saved = os.dup(fd)                                 # fd bandh/invalid ho to OSError
                started.append((fd, saved))
                read_fd, write_fd = os.pipe()
                os.dup2(write_fd, fd)
                os.close(write_fd)
                thread = threading.Thread(target=self._pump, args=(read_fd, saved), daemon=True)
                thread.start()
                self._readers.append((fd, saved, read_fd, thread))
        except Exception:
            for fd, saved in started:                              # jo ho chuka use wapas karo
                try:
                    os.dup2(saved, fd)
                except OSError:
                    pass
            raise
        self.mode = "fd"

    def _stop_fd(self) -> None:
        self._flush_python_and_c()
        for fd, saved, read_fd, thread in self._readers:
            try:
                os.dup2(saved, fd)                                 # asli console wapas; pipe ka write-end band
            except OSError:
                pass
        for fd, saved, read_fd, thread in self._readers:
            thread.join(timeout=2.0)
            for handle in (read_fd, saved):
                try:
                    os.close(handle)
                except OSError:
                    pass
        self._readers = []

    def _start_python(self) -> None:
        self._originals = (sys.stdout, sys.stderr)
        sys.stdout = _Tee(sys.stdout, self._add)
        sys.stderr = _Tee(sys.stderr, self._add)
        root = logging.getLogger()
        if not root.handlers:                                      # warna lastResort hat jaata
            self._handler = _ListHandler(self._add)
            root.addHandler(self._handler)
        self.mode = "python"

    def _stop_python(self) -> None:
        if self._originals is not None:
            sys.stdout, sys.stderr = self._originals
            self._originals = None
        if self._handler is not None:
            logging.getLogger().removeHandler(self._handler)
            self._handler = None

    # ------------------------------------------------------------------
    def __enter__(self) -> "ConsoleCapture":
        self._active = True
        if self.fd_level and self.FD_SUPPORTED:
            try:
                self._start_fd()
            except Exception:  # noqa: BLE001
                self.mode = "none"
        if self.mode == "none":
            try:
                self._start_python()
            except Exception:  # noqa: BLE001
                self.mode = "none"
        return self

    def __exit__(self, *exc) -> bool:
        if self._active:
            try:
                if self.mode == "fd":
                    self._stop_fd()
                elif self.mode == "python":
                    self._stop_python()
            finally:
                self._active = False
        return False


# =============================================================================
# Analysis
# =============================================================================
@dataclass
class Finding:
    level: str                 # error | warning | info
    text: str
    hint: str = ""
    actionable: bool = False

    def line(self) -> str:
        return f"[{self.level}] {self.text}" + (f" -> {self.hint}" if self.hint else "")


_NOISE = re.compile(
    r"blendkit|blenderkit|\[TIMING\]|^\s*Saved:|render\s*\|\s*Saved|^INFO:|^\d\d:\d\d:\d\d \| INFO|^Info:|glTF import finished|"
    r"Data are loaded|Created history step|\[Blender AI Agent\]|Repository data|missing 'bl_info'|^Fra:|^Time:|^Mem:|Read blend|"
    r"ℹ️|Blender create Mesh node|^\s*$|Switched to:|Quadriflow remesh was cancelled|^Warning: add-on|bpy_extras",
    re.IGNORECASE)
_ERROR = re.compile(
    r"Traceback \(most recent call last\)|^\s*(?:\w+\.)*\w*(?:Error|Exception)\b: |\|\s*ERROR\b|^\s*ERROR\b|^Error:|\bFATAL\b|"
    r"Segmentation fault|EXCEPTION_ACCESS_VIOLATION|StructRNA of type \w+ has been removed|Python: File", re.IGNORECASE | re.MULTILINE)
_WARNING = re.compile(r"^\s*Warning\b|\|\s*WARN(?:ING)?\b|^WARNING\b|\b\w*Warning:|\b(?:failed|cannot|could not|can't|no such file|not found|unsupported)\b",
                      re.IGNORECASE)
# (regex, hint, actionable)
_HINTS = [
    (re.compile(r"needs to be manifold|non-?manifold|inconsistent", re.I),
     "mesh is not clean (holes / flipped normals / duplicate points): recalculate normals, merge by distance, remove degenerate faces, or rebuild that part", True),
    (re.compile(r"StructRNA of type \w+ has been removed", re.I),
     "an object was used after it was deleted: look objects up again by name after any delete/join/boolean", True),
    (re.compile(r"DeprecationWarning|FutureWarning|PendingDeprecation", re.I), "informational only (a Blender API is being retired); no fix needed", False),
    (re.compile(r"no such file|file not found|cannot open|missing (?:texture|image|file)|failed to load|(?:texture|image|file|font)\b[^\n]{0,60}\bnot found", re.I),
     "a file/texture could not be found: check the path or re-import", True),
    (re.compile(r"out of memory|memoryerror", re.I), "too heavy: lower the resolution / face count", True),
    (re.compile(r"modifier", re.I), "a modifier reported a problem: check its settings or remove it", True),
    (re.compile(r"Traceback|Error\b|Exception\b", re.I), "a Python error happened: find which step failed and redo it differently", True),
]


def analyze_console(text: str, max_findings: int = 8) -> List[Finding]:
    """Console text -> shor hata kar, duplicate hata kar, Finding list (errors pehle)."""
    findings: List[Finding] = []
    seen = set()
    lines = (text or "").replace("\r", "").split("\n")
    for index, raw in enumerate(lines):
        line = raw.strip()
        if not line or _NOISE.search(line):
            continue
        if _ERROR.search(line):
            level = "error"
        elif _WARNING.search(line):
            level = "warning"
        else:
            continue
        if line.startswith("File ") or line.startswith("^"):            # traceback ke andar ki lines: Traceback line hi kaafi
            continue
        # traceback ho to aakhri "XError: ..." line bhi saath dikhao
        if re.search(r"Traceback \(most recent call last\)", line):
            tail = next((l.strip() for l in lines[index + 1:index + 40] if re.match(r"^\s*(?:\w+\.)*\w*(?:Error|Exception)\b: ", l)), "")
            line = (line + " ... " + tail) if tail else line
        short = re.sub(r"\s+", " ", line)[:220]
        key = re.sub(r"\d+", "#", short)
        if key in seen:
            continue
        seen.add(key)
        hint, actionable = "", level == "error"
        for pattern, text_hint, is_action in _HINTS:
            if pattern.search(line):
                hint, actionable = text_hint, is_action
                if not is_action:
                    level = "info"
                break
        if level == "warning" and not hint:
            continue                                                    # bina wajah wali generic warning: shor
        findings.append(Finding(level, short, hint, actionable))
    order = {"error": 0, "warning": 1, "info": 2}
    findings.sort(key=lambda f: order[f.level])
    return findings[:max_findings]