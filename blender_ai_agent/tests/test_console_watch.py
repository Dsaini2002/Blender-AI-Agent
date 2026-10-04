import ctypes
import os
import sys
import tempfile
import unittest
import warnings

from blender_ai_agent.agent.console_watch import ConsoleCapture, analyze_console


def c_write(fd: int, text: str) -> None:
    """Python ke sys.stdout/stderr se bachkar seedha fd par likhta hai (C-level print jaisa)."""
    os.write(fd, text.encode("utf-8"))


class TestAnalyze(unittest.TestCase):

    def test_real_blender_console_lines_from_this_project(self):
        log = """ℹ️  blendkit: Verbose is enabled [16:27:34.008, addon_updater.py:150]
[Blender AI Agent] Registered. Tools: ['scene.inspect']
00:18.015  operator         | ERROR Python:   File "\\Text", line 1
                            |     $a="D:\\x"
                            | SyntaxError: invalid syntax
\\Text:38: DeprecationWarning: 'World.use_nodes' is expected to be removed in Blender 6.0
01:55.594  render           | Saved: 'C:\\Users\\x\\smoke_test.png'
Warning: QuadriFlow: The mesh needs to be manifold and have face normals that point in a consistent direction
16:29:26 | INFO: Data are loaded, start creating Blender stuff
16:29:26 | INFO: glTF import finished in 0.08s
[TIMING]     Gemini attempt 1: 6.56s (ok)
Info: QuadriFlow: Remeshing completed
Warning: add-on missing 'bl_info', this can cause poor performance!: 'C:\\x\\run_tests.py'
"""
        findings = analyze_console(log)
        levels = [(f.level, f.actionable) for f in findings]
        self.assertEqual(levels[0], ("error", True))                       # operator ERROR Python
        texts = " | ".join(f.text for f in findings)
        self.assertIn("ERROR Python", texts)
        self.assertIn("needs to be manifold", texts)
        manifold = next(f for f in findings if "manifold" in f.text)
        self.assertEqual((manifold.level, manifold.actionable), ("warning", True))
        self.assertIn("normals", manifold.hint)
        deprecation = next(f for f in findings if "DeprecationWarning" in f.text)
        self.assertEqual((deprecation.level, deprecation.actionable), ("info", False))
        for noise in ("blendkit", "Saved:", "TIMING", "glTF import finished", "Remeshing completed", "bl_info", "Registered"):
            self.assertNotIn(noise, texts)

    def test_tracebacks_show_the_final_error_line(self):
        text = ("Traceback (most recent call last):\n  File \"x.py\", line 3, in <module>\n    foo()\n"
                "ReferenceError: StructRNA of type Object has been removed\n")
        findings = analyze_console(text)
        self.assertEqual(len(findings), 2)                                   # Traceback + (alag) ReferenceError line, dono error
        joined = " ".join(f.text for f in findings)
        self.assertIn("StructRNA", joined)
        self.assertTrue(all(f.level == "error" for f in findings))
        self.assertIn("deleted", next(f for f in findings if "StructRNA" in f.text).hint)

    def test_dedupe_cap_and_ordering(self):
        text = "\n".join(f"Warning: texture image_{i}.png not found" for i in range(30)) + "\nRuntimeError: boom\n"
        findings = analyze_console(text)
        self.assertEqual(findings[0].level, "error")                         # error pehle
        self.assertLessEqual(len(findings), 8)
        self.assertEqual(sum(1 for f in findings if "not found" in f.text), 1)   # numbers ek jaise => ek hi

    def test_quiet_and_unknown_text(self):
        self.assertEqual(analyze_console(""), [])
        self.assertEqual(analyze_console(None), [])
        self.assertEqual(analyze_console("hello world\nall fine\nDone in 2.1s"), [])
        self.assertEqual(analyze_console("Warning: something odd happened"), [])      # bina hint ki generic warning = shor


FD_OK = ConsoleCapture.FD_SUPPORTED


class TestCapture(unittest.TestCase):

    def test_windows_rule_forces_python_level_capture(self):
        """Windows par fd-level capture print() ko tod deta hai (WinError 1): wahan hamesha Python-level."""
        original = ConsoleCapture.FD_SUPPORTED
        ConsoleCapture.FD_SUPPORTED = False
        try:
            before = (sys.stdout, sys.stderr)
            import io
            sink = io.StringIO()
            sys.stdout = sink
            try:
                with ConsoleCapture(fd_level=True) as cap:
                    print("printing works")
                    sys.stderr.write("Error: also works\n")
            finally:
                sys.stdout = before[0]
            self.assertEqual(cap.mode, "python")
            self.assertIn("printing works", cap.text())
            self.assertIn("printing works", sink.getvalue())                       # console par bhi pahunchi
            self.assertEqual((sys.stdout, sys.stderr), before)
        finally:
            ConsoleCapture.FD_SUPPORTED = original
        self.assertEqual(ConsoleCapture.FD_SUPPORTED, os.name != "nt")

    @unittest.skipUnless(FD_OK, "fd-level capture Windows par band hai")
    def test_fd_level_catches_c_style_writes_and_still_shows_them(self):
        shown = tempfile.TemporaryFile()
        saved_1, saved_2 = os.dup(1), os.dup(2)
        os.dup2(shown.fileno(), 1)                                            # "asli console" = yeh file
        os.dup2(shown.fileno(), 2)
        try:
            with ConsoleCapture(fd_level=True) as cap:
                c_write(2, "Warning: QuadriFlow: The mesh needs to be manifold\n")
                c_write(1, "plain stdout line\n")
                print("python print line", flush=True)
                libc = ctypes.CDLL(None)
                libc.puts(b"printf style from C")
            mode = cap.mode
        finally:
            os.dup2(saved_1, 1); os.dup2(saved_2, 2); os.close(saved_1); os.close(saved_2)
        shown.seek(0)
        passthrough = shown.read().decode()
        shown.close()
        self.assertEqual(mode, "fd")
        text = cap.text()
        for line in ("needs to be manifold", "plain stdout line", "python print line", "printf style from C"):
            self.assertIn(line, text)
            self.assertIn(line, passthrough)                                   # user ke console par bhi pahunchi

    @unittest.skipUnless(FD_OK, "fd-level capture Windows par band hai")
    def test_fd_capture_restores_the_streams_and_is_reusable(self):
        before = (os.fstat(1).st_ino, os.fstat(2).st_ino)
        for _ in range(3):
            with ConsoleCapture(fd_level=True) as cap:
                c_write(2, "once more\n")
            self.assertIn("once more", cap.text())
        self.assertEqual((os.fstat(1).st_ino, os.fstat(2).st_ino), before)

    def test_python_level_fallback_catches_print_stderr_and_warnings(self):
        original_out, original_err = sys.stdout, sys.stderr
        with ConsoleCapture(fd_level=False) as cap:
            print("hello from print")
            sys.stderr.write("Error: from stderr\n")
            warnings.warn("old api", DeprecationWarning)
        self.assertEqual(cap.mode, "python")
        self.assertIs(sys.stdout, original_out)
        self.assertIs(sys.stderr, original_err)                                # wapas pehle jaisa
        self.assertIn("hello from print", cap.text())
        self.assertIn("Error: from stderr", cap.text())

    def test_failure_to_start_falls_back_instead_of_raising(self):
        class Broken(ConsoleCapture):
            def _start_fd(self):
                raise OSError("no console")
        with Broken(fd_level=True) as cap:
            print("still captured")
        self.assertEqual(cap.mode, "python")
        self.assertIn("still captured", cap.text())

    @unittest.skipUnless(FD_OK, "fd-level capture Windows par band hai")
    def test_exceptions_inside_the_block_propagate_and_streams_are_restored(self):
        before = os.fstat(2).st_ino
        with self.assertRaises(ValueError):
            with ConsoleCapture(fd_level=True):
                raise ValueError("task crashed")
        self.assertEqual(os.fstat(2).st_ino, before)

    def test_size_cap(self):
        import io
        real_out, sink = sys.stdout, io.StringIO()
        sys.stdout = sink                                                     # test ka shor user ke terminal par na aaye
        try:
            cap = ConsoleCapture(fd_level=False)
            cap.MAX_CHARS = 1000
            with cap:
                for _ in range(500):
                    print("x" * 100)
        finally:
            sys.stdout = real_out
        self.assertLessEqual(len(cap.text()), 1100)
        self.assertGreater(len(sink.getvalue()), 40000)                       # par console par sab kuch pahuncha


if __name__ == "__main__":
    unittest.main()