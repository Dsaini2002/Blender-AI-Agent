import math
import unittest

from blender_ai_agent.tools import mesh_engine as me
from blender_ai_agent.tools.mesh_script import ScriptError, compile_script, run_script
from .test_mesh_kit_engine import bottle, cube, finite


def info_for(verts_faces):
    return me.analyze(*verts_faces)


class TestSandboxAllowsMath(unittest.TestCase):

    def test_simple_displacement(self):
        verts, faces = bottle()
        result = run_script(info_for((verts, faces)), "dz = 0.1 * sin(u * 6.0)")
        self.assertTrue(result.moves)
        i = next(iter(result.moves))
        self.assertAlmostEqual(result.moves[i][2] - verts[i][2], 0.1 * math.sin(((verts[i][0] + 0.4) / 0.8) * 6.0), places=9)

    def test_inputs_are_available_and_normalised(self):
        verts, faces = bottle()
        result = run_script(info_for((verts, faces)), "dx = w * 0.0 + u * 0.0 + v * 0.0 + (size - 3.0) + (cz - 1.5) + (n - 280) + (maxz - 3.0) + (minz)")
        self.assertEqual(result.moves, {})                                 # sab 0 => kuch nahi hila

    def test_reassigning_x_y_z_moves_the_vertex(self):
        verts, faces = cube()
        result = run_script(info_for((verts, faces)), "z = z * 2")
        self.assertAlmostEqual(max(p[2] for i, p in result.moves.items()), 2.0)

    def test_if_elif_else_for_loops_and_functions(self):
        verts, faces = bottle()
        code = ("s = 0.0\nfor k in range(4):\n    s += 0.01 * sin(k + u * 5)\n"
                "if w > 0.5:\n    dz = s\nelif w > 0.25:\n    dz = -s\nelse:\n    dz = 0.0\n")
        result = run_script(info_for((verts, faces)), code)
        self.assertTrue(result.moves)
        self.assertTrue(finite(list(result.moves.values())))

    def test_noise_rand_and_helper_functions(self):
        verts, faces = bottle()
        code = "dz = 0.02 * fbm(u * 5, v * 5, w * 5) + 0.01 * (noise(i, 0, 0) + rand(i)) + lerp(0, 0.01, smoothstep(0.0, 1.0, w)) * clamp(u, 0, 1)"
        result = run_script(info_for((verts, faces)), code)
        self.assertTrue(result.moves)

    def test_selection_and_weights_are_respected(self):
        verts, faces = bottle()
        top_only = run_script(info_for((verts, faces)), "dz = 0.5", select="top")
        weights = me.selection_weights("top", info_for((verts, faces)))
        self.assertTrue(all(weights[i] > 0 for i in top_only.moves))
        half = run_script(info_for((verts, faces)), "dz = 1.0", select={"region": "top", "strength": 0.5})
        i = max(half.moves, key=lambda k: half.moves[k][2] - verts[k][2])
        self.assertAlmostEqual(half.moves[i][2] - verts[i][2], 0.5, places=6)

    def test_remove_deletes_faces(self):
        verts, faces = bottle()
        result = run_script(info_for((verts, faces)), "if w > 0.9:\n    remove = 1")
        self.assertTrue(result.remove_faces)
        self.assertTrue(all(any(verts[v][2] > 0.9 * 3.0 for v in faces[f]) for f in result.remove_faces))

    def test_math_errors_on_a_few_vertices_are_skipped_not_fatal(self):
        verts, faces = bottle()
        result = run_script(info_for((verts, faces)), "dz = 0.01 / (i - 3)")        # i == 3: ZeroDivisionError
        self.assertIn("skipped", result.note)
        self.assertTrue(result.moves)

    def test_runs_inside_the_pipeline(self):
        verts, faces = bottle()
        result = me.apply_ops(verts, faces, [{"op": "script", "code": "dz = 0.05 * w", "select": "top"}])
        self.assertFalse(result.topology_changed)
        self.assertGreater(max(v[2] for v in result.vertices), 3.0)


class TestSandboxBlocksEverythingElse(unittest.TestCase):

    def assertBlocked(self, code, fragment=None):
        with self.assertRaises(ScriptError, msg=code) as ctx:
            compile_script(code)
        if fragment:
            self.assertIn(fragment, str(ctx.exception), code)

    def test_imports_attributes_dunders_and_builtins(self):
        for code in ("import os", "from os import system", "x = (1).__class__", "x = ().__class__.__bases__",
                     "dx = math.sin(1)", "dx = open('f')", "dx = eval('1')", "dx = exec('1')", "dx = __import__('os')",
                     "dx = getattr(x, 'a')", "dx = print(1)", "dx = len(x)", "_a = 1", "dx = _a"):
            self.assertBlocked(code)

    def test_forbidden_statements_and_expressions(self):
        for code in ("while True:\n    dx = 1", "def f():\n    pass", "class A:\n    pass", "dx = lambda: 1", "dx = [1, 2][0]",
                     "dx = (1, 2)", "dx = {1: 2}", "dx = 'text'", "dx = [i for i in range(3)]", "try:\n    pass\nexcept:\n    pass",
                     "with x:\n    pass", "global x", "del x", "assert 1", "raise ValueError", "dx = x if y else (z)\nreturn 1",
                     "dx = f'{x}'", "dx = x.real", "dx = x[0]", "sin(1)", "yield 1", "dx := 1"):
            self.assertBlocked(code)

    def test_unknown_names_function_misuse_and_shadowing(self):
        self.assertBlocked("dx = foo", "unknown name")
        self.assertBlocked("dx = sin", "function")
        self.assertBlocked("dx = foo(1)", "only these functions")
        self.assertBlocked("sin = 3", "cannot assign")
        self.assertBlocked("pi = 3", "cannot assign")
        self.assertBlocked("dx = sin(x=1)", "positional")

    def test_resource_limits(self):
        self.assertBlocked("for k in range(100):\n    dx += 1", "at most 32")
        self.assertBlocked("for a in range(8):\n    for b in range(8):\n        for c in range(2):\n            dx += 1", "at most 64")
        self.assertBlocked("for k in range(n):\n    dx += 1", "range")
        self.assertBlocked("dx = x ** 99", "exponent")
        self.assertBlocked("dx = x ** y", "exponent")
        self.assertBlocked("dx = 1\n" * 2000, "too long")
        self.assertBlocked("", "empty")
        self.assertBlocked("   \n", "empty")
        self.assertBlocked("dx = ", "syntax")

    def test_cannot_escape_through_builtins(self):
        function = compile_script("dx = 1")
        self.assertEqual(function.__globals__["__builtins__"], {})

    def test_exponent_and_small_loops_are_allowed(self):
        compile_script("dx = x ** 2 + y ** -1 + pow(x, 40)")
        compile_script("for k in range(3, 9):\n    dx += k")
        compile_script("for a in range(4):\n    for b in range(4):\n        dx += 1")

    def test_runtime_guards(self):
        verts, faces = bottle()
        info = info_for((verts, faces))
        with self.assertRaises(ScriptError):
            run_script(info, "dz = 1 / (x - x)")                                 # har vertex par ZeroDivisionError => fail
        with self.assertRaises(ScriptError) as ctx:
            run_script(info, "dz = 0.001", time_limit=-1.0)
        self.assertIn("slow", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()