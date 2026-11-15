"""Props in the middle of paths, and paths through the pond (log 20261114_141802: the benches were
placed at (-6, 2) and (6, -2) - right on park_path2 - and a lamp at (-8, -8) on park_path1; both
paths ran through the central duck pond). Also the vision check's bare FileNotFoundError."""

from . import _bpy_stub  # noqa: F401

import math
import unittest
from unittest.mock import patch

from blender_ai_agent import net
from blender_ai_agent.agent import self_correct as sc
from blender_ai_agent.agent.scene_checks import geometry_problems
from blender_ai_agent.tests.fakes import FakeObject
from blender_ai_agent.tools import paths
from blender_ai_agent.tools.curve_tools import CreateCurveTool
from blender_ai_agent.tools.library_tools import LibraryPlaceTool
from blender_ai_agent.tools.placement_tools import MoveOffPathTool
from .test_library_recipes import NodeBridge, _ensure_lights

_ensure_lights(NodeBridge)

PATH1 = [[-10.0, -10.0, 0.0], [-5.0, -2.0, 0.0], [0.0, 2.0, 0.0], [5.0, 6.0, 0.0], [10.0, 12.0, 0.0]]
PATH2 = [[-12.0, 8.0, 0.0], [-6.0, 2.0, 0.0], [0.0, 0.0, 0.0], [6.0, -4.0, 0.0], [12.0, -10.0, 0.0]]


def park_bridge():
    paths.clear()
    bridge = NodeBridge()
    tool = CreateCurveTool(bridge)
    for name, pts in (("park_path1", PATH1), ("park_path2", PATH2)):
        result = tool.execute({"name": name, "points": pts, "profile": "flat", "width": 2.0, "location": [0, 0, 0.02]})
        assert result.success, result.error
    return bridge


def box_obj(name, center, size, z0=0.0, material="m"):
    o = FakeObject(name=name, location=[center[0], center[1], z0])
    o.fake_bbox = {"min": [-size[0] / 2, -size[1] / 2, 0.0], "max": [size[0] / 2, size[1] / 2, size[2]]}
    o.material_name = material
    return o


class TestPathMath(unittest.TestCase):

    def setUp(self):
        paths.clear()

    def test_clear_spot_moves_to_the_edge(self):
        paths.register("p", [[(-10, 0), (10, 0)]], width=2.0)
        x, y, off, facing = paths.clear_spot(3.0, 0.2, 0.3, paths.live_paths())
        self.assertEqual(off, ["p"])
        self.assertAlmostEqual(x, 3.0)
        self.assertAlmostEqual(y, 1.0 + 0.3 + paths.EDGE_GAP)
        self.assertAlmostEqual(facing[1], -1.0)                # looks back towards the path

    def test_free_spot_is_unchanged(self):
        paths.register("p", [[(-10, 0), (10, 0)]], width=2.0)
        self.assertEqual(paths.clear_spot(3.0, 5.0, 0.3, paths.live_paths())[:3], (3.0, 5.0, []))

    def test_crossing_paths_are_both_cleared(self):
        paths.register("a", [[(-10, 0), (10, 0)]], width=2.0)
        paths.register("b", [[(0, -10), (0, 10)]], width=2.0)
        x, y, off, _ = paths.clear_spot(0.1, 0.1, 0.3, paths.live_paths())
        self.assertIsNone(paths.on_path(x, y, 0.3, paths.live_paths()))
        self.assertEqual(sorted(off), ["a", "b"])

    def test_bench_yaw_faces_the_path(self):
        # bench front is -Y; a path to the north (+Y) needs a 180 degree turn
        self.assertAlmostEqual(abs(paths.facing_yaw_degrees((0.0, 1.0))), 180.0)
        self.assertAlmostEqual(paths.facing_yaw_degrees((0.0, -1.0)), 0.0)


class TestRegistration(unittest.TestCase):

    def test_paths_register_but_ground_and_water_do_not(self):
        bridge = park_bridge()
        tool = CreateCurveTool(bridge)
        tool.execute({"name": "park_ground", "profile": "flat", "width": 25.0, "closed": True, "curve_type": "POLY",
                      "strokes": [[[-12.5, -12.5, 0], [12.5, -12.5, 0], [12.5, 12.5, 0], [-12.5, 12.5, 0]]]})
        tool.execute({"name": "pond_edge", "profile": "flat", "width": 1.0, "points": [[0, 0, 0], [1, 0, 0]]})
        self.assertEqual(sorted(paths.live_paths(bridge)), ["park_path1", "park_path2"])

    def test_deleted_path_is_forgotten(self):
        bridge = park_bridge()
        bridge.delete_object("park_path1")
        self.assertEqual(list(paths.live_paths(bridge)), ["park_path2"])


class TestLibraryKeepsOffPaths(unittest.TestCase):

    def test_the_logged_bench_and_lamp_are_moved_to_the_edge(self):
        bridge = park_bridge()
        live = paths.live_paths(bridge)
        for model, loc, extra in (("park_bench", [-6.0, 2.0, 0.4], {"yaw_degrees": 45}),
                                  ("street_lamp", [-8.0, -8.0, 0.0], {"height": 3.5})):
            result = LibraryPlaceTool(bridge).execute({"model": model, "location": loc, **extra})
            self.assertTrue(result.success, result.error)
            # the bench was asked for at z=0.4 with nothing under it: it still lands on the path, so it is moved
            self.assertIn("moved_off_path", result.data, model)
            x, y = result.data["location"][:2]
            self.assertIsNone(paths.on_path(x, y, 0.1, live), model)

    def test_something_on_a_table_next_to_a_path_stays_put(self):
        bridge = park_bridge()
        bridge._objects.append(box_obj("picnic_table", (-6.0, 2.0), (1.6, 0.8, 0.75)))
        result = LibraryPlaceTool(bridge).execute({"model": "lantern", "location": [-6.0, 2.0, 0.75]})
        self.assertNotIn("moved_off_path", result.data)

    def test_bench_on_the_ground_faces_the_path(self):
        bridge = park_bridge()
        result = LibraryPlaceTool(bridge).execute({"model": "park_bench", "location": [-6.0, 2.0, 0.0], "yaw_degrees": 45})
        self.assertTrue(result.success, result.error)
        self.assertIn("turned to face the path", result.data["moved_off_path"])
        x, y = result.data["location"][:2]
        hit = paths.nearest(x, y, paths.live_paths(bridge))
        to_path = ((hit["point"][0] - x), (hit["point"][1] - y))
        seat = next(o for o in bridge.get_objects() if o.name == "park_bench_seat_slat1")
        yaw = seat.rotation_euler[2]
        front = (math.sin(yaw), -math.cos(yaw))
        self.assertGreater(front[0] * to_path[0] + front[1] * to_path[1], 0)

    def test_props_away_from_paths_are_untouched(self):
        bridge = park_bridge()
        result = LibraryPlaceTool(bridge).execute({"model": "bush", "location": [8.0, 4.0, 0.0]})
        self.assertNotIn("moved_off_path", result.data)
        self.assertEqual(result.data["location"][:2], [8.0, 4.0])

    def test_no_paths_no_change(self):
        paths.clear()
        result = LibraryPlaceTool(NodeBridge()).execute({"model": "park_bench", "location": [0, 0, 0]})
        self.assertNotIn("moved_off_path", result.data)


class TestMoveOffPathAndChecks(unittest.TestCase):

    def test_tool_moves_all_parts_of_a_model_together(self):
        bridge = park_bridge()
        bridge._objects += [box_obj("bench_seat", (-6.0, 2.0), (1.8, 0.5, 0.5)),
                            box_obj("bench_back", (-6.0, 2.2), (1.8, 0.1, 0.9))]
        before = {n: list(bridge.get_object(n).location) for n in ("bench_seat", "bench_back")}
        result = MoveOffPathTool(bridge).execute({"names": ["bench_seat", "bench_back"]})
        self.assertTrue(result.success, result.error)
        self.assertEqual(len(result.data["moved"]), 1)
        deltas = {n: [bridge.get_object(n).location[k] - before[n][k] for k in range(2)] for n in before}
        self.assertEqual([round(v, 4) for v in deltas["bench_seat"]], [round(v, 4) for v in deltas["bench_back"]])
        self.assertGreater(math.hypot(*deltas["bench_seat"]), 0.5)

    def test_tool_leaves_free_things_alone(self):
        bridge = park_bridge()
        bridge._objects.append(box_obj("rock", (8.0, -1.0), (1.0, 1.0, 0.8)))
        result = MoveOffPathTool(bridge).execute({"names": ["rock"]})
        self.assertEqual(result.data["moved"], [])

    def test_check_flags_a_blocker_and_a_path_through_the_pond(self):
        bridge = park_bridge()
        bridge._objects += [box_obj("lamp_pole", (-8.0, -8.0), (0.15, 0.15, 3.5)),
                            box_obj("duck_pond", (0.0, 0.0), (8.0, 8.0, 0.2))]
        problems = geometry_problems(bridge, ["lamp_pole", "duck_pond", "park_path1", "park_path2"])
        text = " | ".join(f"{p['where']}: {p['issue']} -> {p['fix']}" for p in problems)
        self.assertIn("lamp_pole: stands in the middle of the path 'park_path1'", text)
        self.assertIn("object.move_off_path(names=['lamp_pole'])", text)
        self.assertIn("runs straight through 'duck_pond'", text)
        self.assertTrue(all(p["severity"] == "high" for p in problems if "path" in p["issue"]))

    def test_clean_layout_has_no_path_problems(self):
        bridge = park_bridge()
        bridge._objects.append(box_obj("rock", (8.0, -1.0), (1.0, 1.0, 0.8)))
        problems = geometry_problems(bridge, ["rock", "park_path1"])
        self.assertFalse([p for p in problems if "path" in p["issue"]])


class TestOwnSslContext(unittest.TestCase):

    def test_urlopen_passes_its_own_context(self):
        with patch("urllib.request.urlopen") as opener:
            net.urlopen("req", timeout=5)
        self.assertIs(opener.call_args.kwargs["context"], net.https_context())

    def test_broken_default_is_retried_without_context(self):
        calls = []

        def fake(request, timeout, **kwargs):
            calls.append(kwargs)
            if "context" in kwargs:
                raise FileNotFoundError(2, "No such file or directory")
            return "ok"

        with patch("urllib.request.urlopen", side_effect=fake):
            self.assertEqual(net.urlopen("req", timeout=5), "ok")
        self.assertEqual(len(calls), 2)

    def test_gemini_client_turns_os_errors_into_a_clear_message(self):
        client = sc.GeminiClient(sc.BuilderConfig(api_key="k"))
        with patch.object(net, "urlopen", side_effect=FileNotFoundError(2, "No such file or directory")):
            with self.assertRaises(sc.BuilderError) as ctx:
                client._request("https://example.invalid/x")
        self.assertIn("secure connection", ctx.exception.user_message)


if __name__ == "__main__":
    unittest.main()
