import os
import struct
import tempfile
import unittest

from blender_ai_agent.image_paths import describe_image, image_format_for, resolve_image_path

TEMP = tempfile.gettempdir()


def temp_file(name):
    return os.path.join(TEMP, name)


class TestResolveOnWindows(unittest.TestCase):
    """Log: render saved C:\\tmp\\room_preview.png but vision looked for '/tmp/room_preview.png'."""

    def resolve(self, path, default="preview.png"):
        return resolve_image_path(path, default, windows=True)

    def test_posix_style_and_rooted_paths_go_to_the_temp_folder(self):
        for given in ("/tmp/room_preview.png", "/tmp/sub/dir/room_preview.png", "\\tmp\\room_preview.png",
                      "~/renders/room_preview.png", "//room_preview.png"):
            self.assertEqual(self.resolve(given), temp_file("room_preview.png"), given)

    def test_bare_and_relative_names_go_to_the_temp_folder(self):
        self.assertEqual(self.resolve("room_preview.png"), temp_file("room_preview.png"))
        self.assertEqual(self.resolve("renders/a.png"), temp_file("a.png"))
        self.assertEqual(self.resolve("renders\\a.png"), temp_file("a.png"))

    def test_real_drive_and_network_paths_are_kept(self):
        for given in ("C:\\renders\\a.png", "D:/shots/a.png", "\\\\server\\share\\a.png"):
            self.assertEqual(self.resolve(given), os.path.normpath(given), given)

    def test_result_is_always_absolute_and_has_an_extension(self):
        for given in ("a", "/tmp/a", "x.v2", "", None, "   ", "/", "/tmp/"):
            result = self.resolve(given)
            self.assertTrue(os.path.isabs(result), repr(given))
            self.assertTrue(result.lower().endswith(".png"), repr(given))

    def test_empty_uses_the_default_name(self):
        self.assertEqual(self.resolve(""), temp_file("preview.png"))
        self.assertEqual(self.resolve(None, "vision_observe.png"), temp_file("vision_observe.png"))
        self.assertEqual(self.resolve("/tmp/"), temp_file("preview.png"))

    def test_quotes_and_spaces_are_stripped(self):
        self.assertEqual(self.resolve('  "/tmp/a.png"  '), temp_file("a.png"))

    def test_other_image_extensions_are_kept(self):
        self.assertEqual(self.resolve("/tmp/a.jpg"), temp_file("a.jpg"))
        self.assertEqual(self.resolve("a.EXR"), temp_file("a.EXR"))

    def test_same_input_gives_the_same_path_for_render_and_vision(self):
        """The whole point: both tools resolve one string to the SAME file."""
        given = "/tmp/room_preview.png"
        self.assertEqual(self.resolve(given, "preview.png"), self.resolve(given, "vision_observe.png"))


class TestResolveOnPosix(unittest.TestCase):

    def resolve(self, path):
        return resolve_image_path(path, "preview.png", windows=False)

    def test_real_absolute_paths_are_untouched(self):
        self.assertEqual(self.resolve("/tmp/room_preview.png"), os.path.normpath("/tmp/room_preview.png"))
        self.assertEqual(self.resolve("/home/me/shots/a.png"), os.path.normpath("/home/me/shots/a.png"))

    def test_relative_goes_to_temp_and_tilde_expands(self):
        self.assertEqual(self.resolve("a.png"), temp_file("a.png"))
        self.assertEqual(self.resolve("sub/a.png"), temp_file("a.png"))
        self.assertTrue(self.resolve("~/a.png").startswith(os.path.expanduser("~")))

    def test_extension_added(self):
        self.assertTrue(self.resolve("/tmp/preview").endswith("preview.png"))


class TestImageFormat(unittest.TestCase):

    def test_format_from_extension(self):
        self.assertEqual(image_format_for("a.png"), "PNG")
        self.assertEqual(image_format_for("a.JPG"), "JPEG")
        self.assertEqual(image_format_for("a.jpeg"), "JPEG")
        self.assertEqual(image_format_for("a.exr"), "OPEN_EXR")
        self.assertEqual(image_format_for("a.tiff"), "TIFF")
        self.assertEqual(image_format_for("a.weird"), "PNG")


class TestDescribeImage(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    def png_bytes(self, width, height):
        return (b"\x89PNG\r\n\x1a\n" + struct.pack(">I", 13) + b"IHDR"
                + struct.pack(">II", width, height) + b"\x08\x06\x00\x00\x00" + b"\x00" * 4)

    def test_real_png_gives_size_and_pixels(self):
        path = os.path.join(self.tmp.name, "a.png")
        with open(path, "wb") as handle:
            handle.write(self.png_bytes(640, 360))
        info = describe_image(path)
        self.assertEqual((info["width"], info["height"]), (640, 360))
        self.assertEqual(info["size_bytes"], os.path.getsize(path))

    def test_non_png_file_gives_only_size(self):
        path = os.path.join(self.tmp.name, "a.jpg")
        with open(path, "wb") as handle:
            handle.write(b"\xff\xd8\xff" + b"\x00" * 30)
        self.assertEqual(set(describe_image(path)), {"size_bytes"})

    def test_missing_directory_or_empty_gives_empty_dict(self):
        self.assertEqual(describe_image(os.path.join(self.tmp.name, "nope.png")), {})
        self.assertEqual(describe_image(self.tmp.name), {})
        self.assertEqual(describe_image(""), {})
        self.assertEqual(describe_image(None), {})

    def test_truncated_png_does_not_crash(self):
        path = os.path.join(self.tmp.name, "short.png")
        with open(path, "wb") as handle:
            handle.write(b"\x89PNG\r\n\x1a\n\x00")
        self.assertEqual(set(describe_image(path)), {"size_bytes"})


if __name__ == "__main__":
    unittest.main()