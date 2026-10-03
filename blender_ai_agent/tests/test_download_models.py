import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

# download_models.py repo ke root mein hai (package ke bahar) — isliye root ko path mein jodte hain.
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import download_models as dm  # noqa: E402

GLB = b"glTF" + b"\x00" * 20


def fake_registry():
    projects = [
        {"id": "pm-momuspark", "name": "MomusPark", "description": "park props", "license": "CC0",
         "asset_data_file": "assets/pm-momuspark.json"},
        {"id": "pm-christmas", "name": "christmas", "description": "xmas", "license": "CC0",
         "asset_data_file": "assets/pm-christmas.json"},
    ]
    assets = {
        "assets/pm-momuspark.json": [
            {"id": "mp-1", "name": "Bench_01_Art", "format": "GLB", "is_public": True, "is_draft": False,
             "model_file_url": "https://x/MomusPark/Bench_01_Art.glb",
             "metadata": {"file_size": len(GLB), "attributes": [{"trait_type": "Type", "value": "Bench"},
                                                                {"trait_type": "Theme", "value": "Nature Park"}]}},
            {"id": "mp-2", "name": "FireTorch01", "format": "GLB", "is_public": True,
             "model_file_url": "https://x/MomusPark/FireTorch01.glb", "metadata": {"file_size": 5_000_000}},
            {"id": "mp-draft", "name": "Draft", "is_draft": True, "model_file_url": "https://x/Draft.glb"},
            {"id": "mp-img", "name": "Pic", "model_file_url": "https://x/Pic.png"},
        ],
        "assets/pm-christmas.json": [
            {"id": "xm-1", "name": "Candle", "format": "GLB", "model_file_url": "https://x/christmas/Candle.glb",
             "metadata": {"file_size": len(GLB)}},
        ],
    }
    return projects, assets


def fake_fetch_json(url):
    projects, assets = fake_registry()
    if url.endswith("projects.json"):
        return projects
    return assets[url.split("/data/")[1]]


class TestRegistryParsing(unittest.TestCase):

    def test_entries_skip_drafts_and_non_models_and_carry_search_tags(self):
        projects, assets = dm.load_registry(fake_fetch_json)
        entries = dm.build_entries(projects, assets)
        names = [e["name"] for e in entries]
        self.assertEqual(names, ["Bench_01_Art", "FireTorch01", "Candle"])
        bench = entries[0]
        self.assertEqual(bench["file"], "MomusPark/Bench_01_Art.glb")
        self.assertEqual(bench["license"], "CC0")
        self.assertIn("bench", bench["tags"])
        self.assertIn("nature", bench["tags"])
        self.assertEqual(bench["attributes"]["Type"], "Bench")
        self.assertIn("torch", entries[1]["tags"])
        self.assertIn("fire", entries[1]["tags"])

    def test_select_projects_by_name_or_id_substring(self):
        projects, assets = dm.load_registry(fake_fetch_json)
        self.assertEqual([p["name"] for p in dm.select_projects(projects, ["momus"])], ["MomusPark"])
        self.assertEqual([p["name"] for p in dm.select_projects(projects, ["pm-christ"])], ["christmas"])
        self.assertEqual(len(dm.select_projects(projects, [])), 2)
        self.assertEqual(dm.select_projects(projects, ["nope"]), [])

    def test_max_mb_skips_big_files(self):
        projects, assets = dm.load_registry(fake_fetch_json)
        names = [e["name"] for e in dm.build_entries(projects, assets, max_mb=1)]
        self.assertNotIn("FireTorch01", names)

    def test_safe_name_and_words(self):
        self.assertEqual(dm.safe_name("a b/c:d.glb"), "a_b_c_d.glb")
        self.assertEqual(dm.split_words("FireTorch01_Art"), ["fire", "torch", "01", "art"])


class TestDownload(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dest = Path(self.tmp.name)
        projects, assets = dm.load_registry(fake_fetch_json)
        self.entries = dm.build_entries(projects, assets)

    def tearDown(self):
        self.tmp.cleanup()

    def test_downloads_then_skips_on_rerun(self):
        calls = []

        def fetch(url):
            calls.append(url)
            return GLB

        entry = self.entries[0]
        self.assertEqual(dm.download_entry(entry, self.dest, fetch), "downloaded")
        self.assertTrue((self.dest / entry["file"]).is_file())
        self.assertFalse(list(self.dest.rglob("*.part")))          # no half-written files left
        self.assertEqual(dm.download_entry(entry, self.dest, fetch), "skipped")
        self.assertEqual(len(calls), 1)
        self.assertEqual(dm.download_entry(entry, self.dest, fetch, force=True), "downloaded")

    def test_wrong_size_file_is_redownloaded(self):
        entry = self.entries[0]
        target = self.dest / entry["file"]
        target.parent.mkdir(parents=True)
        target.write_bytes(b"glTFshort")                           # truncated earlier download
        self.assertEqual(dm.download_entry(entry, self.dest, lambda u: GLB), "downloaded")
        self.assertEqual(target.read_bytes(), GLB)

    def test_invalid_or_failed_downloads_are_reported_not_written(self):
        entry = self.entries[0]
        self.assertTrue(dm.download_entry(entry, self.dest, lambda u: b"<html>oops").startswith("failed"))

        def boom(url):
            raise RuntimeError("network down")

        self.assertIn("network down", dm.download_entry(entry, self.dest, boom))
        self.assertFalse((self.dest / entry["file"]).exists())

    def test_index_lists_only_files_that_exist(self):
        dm.download_entry(self.entries[0], self.dest, lambda u: GLB)
        count = dm.write_index(self.dest, self.entries)
        data = json.loads((self.dest / "index.json").read_text(encoding="utf-8"))
        self.assertEqual(count, 1)
        self.assertEqual([m["name"] for m in data["models"]], ["Bench_01_Art"])
        self.assertIn("CC0", data["license"])


class TestCommandLine(unittest.TestCase):

    def _run(self, argv, answers=("y",)):
        lines, prompts = [], list(answers)
        code = dm.run(argv, fetch_json_fn=fake_fetch_json, fetch_bytes_fn=lambda u: GLB,
                      input_fn=lambda _: prompts.pop(0), out=lines.append)
        return code, "\n".join(lines)

    def test_list_does_not_download(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, text = self._run(["--list", "--dest", tmp])
            self.assertEqual(code, 0)
            self.assertIn("MomusPark", text)
            self.assertFalse((Path(tmp) / "index.json").exists())

    def test_full_run_downloads_everything_and_writes_index(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, text = self._run(["--dest", tmp, "--yes"])
            self.assertEqual(code, 0, text)
            index = json.loads((Path(tmp) / "index.json").read_text(encoding="utf-8"))
            self.assertEqual(index["count"], 3)
            self.assertTrue((Path(tmp) / "christmas" / "Candle.glb").is_file())

    def test_only_filter_and_confirmation_prompt(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, _ = self._run(["--dest", tmp, "--only", "christmas"], answers=("n",))
            self.assertEqual(code, 1)                                # user said no -> nothing downloaded
            self.assertFalse((Path(tmp) / "christmas").exists())
            code, _ = self._run(["--dest", tmp, "--only", "christmas"], answers=("y",))
            self.assertEqual(code, 0)
            self.assertTrue((Path(tmp) / "christmas" / "Candle.glb").is_file())
            self.assertFalse((Path(tmp) / "MomusPark").exists())

    def test_unknown_collection_is_a_clear_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, text = self._run(["--dest", tmp, "--only", "zzz", "--yes"])
            self.assertEqual(code, 2)
            self.assertIn("--list", text)

    def test_failures_give_nonzero_exit_but_keep_good_files(self):
        def flaky(url):
            if "Candle" in url:
                raise RuntimeError("boom")
            return GLB

        with tempfile.TemporaryDirectory() as tmp:
            lines = []
            code = dm.run(["--dest", tmp, "--yes", "--workers", "1"], fetch_json_fn=fake_fetch_json,
                          fetch_bytes_fn=flaky, input_fn=lambda _: "y", out=lines.append)
            self.assertEqual(code, 3)
            index = json.loads((Path(tmp) / "index.json").read_text(encoding="utf-8"))
            self.assertNotIn("Candle", [m["name"] for m in index["models"]])
            self.assertIn("Bench_01_Art", [m["name"] for m in index["models"]])
            self.assertTrue(any("FAIL Candle" in line for line in lines))

    def test_env_var_sets_default_destination(self):
        os.environ["BLENDER_AI_MODELS_DIR"] = "~/somewhere_else"
        try:
            self.assertEqual(dm.default_dest(), Path("~/somewhere_else").expanduser())
        finally:
            del os.environ["BLENDER_AI_MODELS_DIR"]


if __name__ == "__main__":
    unittest.main()