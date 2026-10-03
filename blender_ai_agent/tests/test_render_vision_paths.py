from . import _bpy_stub  # noqa: F401

import os
import struct
import tempfile
import unittest
from types import SimpleNamespace

from blender_ai_agent.image_paths import resolve_image_path
from blender_ai_agent.tools.camera_tools import RenderPreviewTool
from blender_ai_agent.tools.models import RenderPreviewInput
from blender_ai_agent.vision.tool import VisionObserveInput, VisionObserveTool

TEMP = tempfile.gettempdir()


def png_bytes(width, height):
    return (b"\x89PNG\r\n\x1a\n" + struct.pack(">I", 13) + b"IHDR"
            + struct.pack(">II", width, height) + b"\x08\x06\x00\x00\x00" + b"\x00" * 4)


class RecordingBridge:
    """render_preview ko bas record karta hai (purane bridge jaisa: sirf filepath, resolution tabhi jab ho)."""

    def __init__(self, write_png=None):
        self.calls = []
        self._write_png = write_png

    def render_preview(self, filepath, **kwargs):
        self.calls.append((filepath, kwargs))
        if self._write_png:
            with open(filepath, "wb") as handle:
                handle.write(png_bytes(*self._write_png))
        return filepath


class TestRenderPreviewInput(unittest.TestCase):

    def test_plain_filepath_keeps_working(self):
        data = RenderPreviewInput(filepath="a.png")
        self.assertEqual(data.filepath, "a.png")
        self.assertIsNone(data.resolution())
        self.assertFalse(data.draft)

    def test_empty_filepath_is_rejected(self):
        for bad in ("", "   ", None, 5):
            with self.assertRaises(ValueError, msg=repr(bad)):
                RenderPreviewInput(filepath=bad)

    def test_draft_and_sizes(self):
        self.assertEqual(RenderPreviewInput(filepath="a.png", draft=True).resolution(), (640, 360))
        self.assertEqual(RenderPreviewInput(filepath="a.png", draft="true").resolution(), (640, 360))
        self.assertEqual(RenderPreviewInput(filepath="a.png", width=1280, height=720).resolution(), (1280, 720))
        self.assertEqual(RenderPreviewInput(filepath="a.png", width=800).resolution(), (800, 450))   # 16:9
        self.assertEqual(RenderPreviewInput(filepath="a.png", height=540).resolution(), (960, 540))
        # explicit size beats draft
        self.assertEqual(RenderPreviewInput(filepath="a.png", draft=True, width=100, height=50).resolution(), (100, 50))

    def test_llm_style_numbers(self):
        data = RenderPreviewInput(filepath="a.png", width="640.0", height=360.0)
        self.assertEqual(data.resolution(), (640, 360))

    def test_size_limits(self):
        for kwargs in ({"width": 8}, {"width": 100000}, {"height": 0}, {"width": "wide"}, {"draft": "maybe"}):
            with self.assertRaises(ValueError, msg=str(kwargs)):
                RenderPreviewInput(filepath="a.png", **kwargs)


class TestRenderPreviewTool(unittest.TestCase):

    def test_plain_call_is_unchanged_for_old_bridges(self):
        bridge = RecordingBridge()
        result = RenderPreviewTool(bridge).execute({"filepath": "room_preview.png"})
        self.assertTrue(result.success, result.error)
        self.assertEqual(bridge.calls, [("room_preview.png", {})])          # no new kwargs sent
        self.assertEqual(result.data, {"filepath": "room_preview.png"})     # file not on disk -> output unchanged

    def test_draft_asks_for_a_small_render(self):
        bridge = RecordingBridge()
        RenderPreviewTool(bridge).execute({"filepath": "a.png", "draft": True})
        self.assertEqual(bridge.calls, [("a.png", {"resolution": (640, 360)})])

    def test_result_carries_proof_when_the_file_really_exists(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "shot.png")
            result = RenderPreviewTool(RecordingBridge(write_png=(640, 360))).execute({"filepath": path})
            self.assertTrue(result.success, result.error)
            self.assertEqual(result.data["filepath"], path)
            self.assertEqual((result.data["width"], result.data["height"]), (640, 360))
            self.assertGreater(result.data["size_bytes"], 0)

    def test_description_tells_the_model_what_to_do(self):
        description = RenderPreviewTool(RecordingBridge()).description
        for word in ("plain file name", "vision.observe", "draft"):
            self.assertIn(word, description)


class FakeAnalyzer:
    def __init__(self, fail_first_with=None, confidence=0.9):
        self.calls = []
        self._fail_first_with = fail_first_with
        self._confidence = confidence

    def observe(self, filepath, context):
        self.calls.append(filepath)
        if self._fail_first_with is not None and len(self.calls) == 1:
            raise self._fail_first_with
        return SimpleNamespace(description="a room", objects_detected=["floor"], issues=[],
                               confidence=self._confidence, is_low_confidence=self._confidence < 0.5)


class TestVisionObserveTool(unittest.TestCase):

    def test_the_exact_log_failure_path_is_resolved_like_render(self):
        """Log: vision.observe failed with Errno 2 on '/tmp/room_preview.png'."""
        analyzer = FakeAnalyzer()
        result = VisionObserveTool(analyzer).execute({"filepath": "/tmp/room_preview.png"})
        self.assertTrue(result.success, result.error)
        self.assertEqual(analyzer.calls, [resolve_image_path("/tmp/room_preview.png", "vision_observe.png")])
        if os.name == "nt":                                   # Windows: always the Temp folder
            self.assertEqual(analyzer.calls, [os.path.join(TEMP, "room_preview.png")])

    def test_bare_filename_becomes_an_absolute_temp_path(self):
        analyzer = FakeAnalyzer()
        VisionObserveTool(analyzer).execute({"filepath": "room_preview.png"})
        self.assertEqual(analyzer.calls, [os.path.join(TEMP, "room_preview.png")])
        self.assertTrue(os.path.isabs(analyzer.calls[0]))

    def test_default_path_is_unchanged(self):
        analyzer = FakeAnalyzer()
        VisionObserveTool(analyzer).execute({})
        self.assertEqual(analyzer.calls, [VisionObserveInput().filepath])
        self.assertEqual(analyzer.calls, [os.path.join(TEMP, "vision_observe.png")])

    def test_real_drive_paths_are_left_alone(self):
        analyzer = FakeAnalyzer()
        VisionObserveTool(analyzer).execute({"filepath": "C:\\shots\\a.png"})
        expected = os.path.normpath("C:\\shots\\a.png") if os.name == "nt" else "C:\\shots\\a.png"
        # On Linux a drive path is just a relative name (-> Temp); on Windows it is kept as-is.
        if os.name == "nt":
            self.assertEqual(analyzer.calls, [expected])
        else:
            self.assertEqual(analyzer.calls, [resolve_image_path("C:\\shots\\a.png", "vision_observe.png")])

    def test_file_not_found_is_retried_once_in_the_temp_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "elsewhere.png")
            analyzer = FakeAnalyzer(fail_first_with=FileNotFoundError(2, "No such file"))
            result = VisionObserveTool(analyzer).execute({"filepath": path})
            self.assertTrue(result.success, result.error)
            self.assertEqual(analyzer.calls, [path, os.path.join(TEMP, "elsewhere.png")])

    def test_file_not_found_in_the_temp_folder_itself_still_fails_cleanly(self):
        analyzer = FakeAnalyzer(fail_first_with=FileNotFoundError(2, "No such file"))
        result = VisionObserveTool(analyzer).execute({"filepath": "missing.png"})
        self.assertFalse(result.success)
        self.assertEqual(len(analyzer.calls), 1)                 # no pointless second try

    def test_other_errors_are_not_retried(self):
        analyzer = FakeAnalyzer(fail_first_with=RuntimeError("429 quota"))
        result = VisionObserveTool(analyzer).execute({"filepath": "a.png"})
        self.assertFalse(result.success)
        self.assertIn("429", result.error)
        self.assertEqual(len(analyzer.calls), 1)

    def test_result_shape_is_unchanged_without_a_file_and_has_proof_with_one(self):
        analyzer = FakeAnalyzer()
        plain = VisionObserveTool(analyzer).execute({"filepath": "no_such_image_xyz.png"})
        self.assertEqual(set(plain.data), {"description", "objects_detected", "issues", "confidence"})

        path = os.path.join(TEMP, "vision_proof_test.png")
        try:
            with open(path, "wb") as handle:
                handle.write(png_bytes(320, 180))
            proven = VisionObserveTool(FakeAnalyzer()).execute({"filepath": path})
            self.assertEqual(proven.data["image"]["filepath"], path)
            self.assertEqual((proven.data["image"]["width"], proven.data["image"]["height"]), (320, 180))
        finally:
            os.remove(path)

    def test_low_confidence_flag_still_works(self):
        result = VisionObserveTool(FakeAnalyzer(confidence=0.2)).execute({})
        self.assertTrue(result.data["low_confidence_warning"])

    def test_invalid_source_still_rejected(self):
        self.assertFalse(VisionObserveTool(FakeAnalyzer()).execute({"source": "x-ray"}).success)


class TestRenderThenVisionAgree(unittest.TestCase):
    """End to end idea: the same LLM-supplied string must lead render and vision to the same file."""

    def test_same_file_for_both_tools(self):
        given = "/tmp/room_preview.png"
        bridge = RecordingBridge()
        analyzer = FakeAnalyzer()
        RenderPreviewTool(bridge).execute({"filepath": given})
        VisionObserveTool(analyzer).execute({"filepath": given})
        # the bridge resolves with resolve_image_path (see bridge.render_preview); the vision tool does the same
        self.assertEqual(resolve_image_path(bridge.calls[0][0], "preview.png"), analyzer.calls[0])


if __name__ == "__main__":
    unittest.main()