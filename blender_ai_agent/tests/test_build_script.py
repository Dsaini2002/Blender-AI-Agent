import math
import unittest

from blender_ai_agent.agent.build_script import (ScriptError, ScriptLimits, function_name, run_script, validate_script)

TOOLS = ["mesh.sdf", "object.create", "object.delete", "material.create", "material.assign", "mesh.lathe"]


class Reply:
    def __init__(self, success=True, data=None, error=None):
        self.success, self.data, self.error = success, data or {}, error


class Recorder:
    """call_tool jaisa: har call record karta hai; naam deta hai."""

    def __init__(self, fail_on=None):
        self.calls = []
        self.fail_on = fail_on or {}

    def __call__(self, tool, kwargs):
        self.calls.append((tool, kwargs))
        if tool in self.fail_on:
            return Reply(False, error=self.fail_on[tool])
        return Reply(True, {"name": kwargs.get("name", "X"), "meshes": [kwargs.get("name", "X")]})


def run(source, recorder=None, **kw):
    recorder = recorder or Recorder()
    return run_script(source, recorder, TOOLS, **kw), recorder


class TestWhatScriptsCanDo(unittest.TestCase):

    def test_tool_calls_with_keyword_arguments_and_return_values(self):
        result, rec = run('r = mesh_sdf(name="Body", resolution=40)\nmaterial_assign(object_name=r["name"], material_name="Paint")')
        self.assertTrue(result.ok, result.error)
        self.assertEqual([c[0] for c in rec.calls], ["mesh.sdf", "material.assign"])
        self.assertEqual(rec.calls[1][1], {"object_name": "Body", "material_name": "Paint"})
        self.assertEqual([c["tool"] for c in result.calls], ["mesh.sdf", "material.assign"])

    def test_loops_functions_comprehensions_fstrings_and_math(self):
        source = '''
def wheel(i, x, y):
    object_create(name=f"Wheel{i}", primitive="CYLINDER", location=[x, y, 0.35], rotation=[math_pi_half(), 0, 0])

def math_pi_half():
    return pi / 2

n = 0
for sx in [1, -1]:
    for sy in [1, -1]:
        wheel(n, 1.3 * sx, 0.8 * sy)
        n += 1
names = [f"Light{k}" for k in range(3)]
pts = [[cos(a) * 2, sin(a) * 2, 0] for a in [radians(d) for d in range(0, 360, 90)]]
note("made", n, "wheels")
object_create(name=names[2], primitive="CUBE", location=pts[1])
'''
        result, rec = run(source)
        self.assertTrue(result.ok, result.error)
        self.assertEqual([c[1]["name"] for c in rec.calls], ["Wheel0", "Wheel1", "Wheel2", "Wheel3", "Light2"])
        self.assertAlmostEqual(rec.calls[0][1]["rotation"][0], math.pi / 2)
        self.assertAlmostEqual(rec.calls[4][1]["location"][1], 2.0)
        self.assertEqual(result.log, ["made"])
        self.assertGreater(result.ticks, 5)

    def test_conditionals_dicts_slices_and_kwargs_unpacking(self):
        source = '''
common = {"primitive": "CUBE", "location": [0, 0, 0]}
spec = {"a": 2, "b": 5}
for key in sorted(spec):
    if spec[key] > 3:
        object_create(name="Big" + key, **common)
    elif spec[key] > 1:
        object_create(name="Mid" + key, **common)
items = [1, 2, 3, 4][1:3]
total = sum(items) * 2
x = 10 if total > 5 else 0
object_create(name=str(x) + "_" + str(total), primitive="CUBE", location=[0, 0, 0])
'''
        result, rec = run(source)
        self.assertTrue(result.ok, result.error)
        self.assertEqual([c[1]["name"] for c in rec.calls], ["Mida", "Bigb", "10_10"])

    def test_nested_tuple_unpacking_in_loops_and_assignments(self):
        source = """
for i, (sx, sy) in enumerate([(1, 1), (-1, 1)]):
    object_create(name=f"W{i}", primitive="CUBE", location=[sx, sy, 0])
a, (b, c) = 1, (2, 3)
((d, e), f) = ((4, 5), 6)
rows = [(x, y) for x, (y, z) in [(1, (2, 3))]]
object_create(name=str(a + b + c + d + e + f), primitive="CUBE", location=[rows[0][0], rows[0][1], 0])
"""
        result, rec = run(source)
        self.assertTrue(result.ok, result.error)
        self.assertEqual([c[1]["name"] for c in rec.calls], ["W0", "W1", "21"])
        for bad in ("for (a.b, c) in [(1, 2)]:\n    pass", "for x[0], y in [(1, 2)]:\n    pass", "() = 1"):
            self.assertFalse(run(bad)[0].ok, bad)

    def test_rand_and_clamp_helpers_are_deterministic(self):
        result, rec = run("object_create(name=str(round(rand(3, 7), 6)), primitive='CUBE', location=[clamp(5, 0, 1), lerp(0, 10, 0.5), 0])")
        self.assertTrue(result.ok, result.error)
        again, rec2 = run("object_create(name=str(round(rand(3, 7), 6)), primitive='CUBE', location=[clamp(5, 0, 1), lerp(0, 10, 0.5), 0])")
        self.assertEqual(rec.calls, rec2.calls)
        self.assertEqual(rec.calls[0][1]["location"], [1, 5.0, 0])

    def test_function_name_mapping(self):
        self.assertEqual(function_name("mesh.sdf"), "mesh_sdf")
        self.assertEqual(function_name("object.create"), "object_create")


class TestErrorsAreReportedNotRaised(unittest.TestCase):

    def test_tool_failure_stops_the_script_with_line_and_reason(self):
        result, rec = run('object_create(name="A", primitive="CUBE")\nmesh_sdf(name="B", shapes=[])\nobject_create(name="C", primitive="CUBE")',
                          Recorder(fail_on={"mesh.sdf": "shapes must not be empty"}))
        self.assertFalse(result.ok)
        self.assertEqual(result.error_line, 2)
        self.assertIn("mesh.sdf failed: shapes must not be empty", result.error)
        self.assertTrue(result.error.startswith("line 2:"))
        self.assertEqual(len(rec.calls), 2)                       # C kabhi nahi chala
        self.assertFalse(result.calls[1]["ok"])

    def test_runtime_python_errors_have_a_line_number(self):
        for source, line, fragment in (("a = 1\nb = a / 0", 2, "division by zero"), ("x = [1][5]", 1, "IndexError"),
                                       ("d = {}\ny = d['k']", 2, "KeyError"), ("z = 'a' + 1", 1, "TypeError"),
                                       ("def f():\n    return f()\nf()", 2, "recursion")):
            result, _ = run(source)
            self.assertFalse(result.ok, source)
            self.assertEqual(result.error_line, line, source)
            self.assertIn(fragment, result.error, source)

    def test_syntax_and_unknown_names(self):
        for source, fragment in (("x = (", "syntax error"), ("y = nothing + 1", "unknown name 'nothing'"),
                                 ("unknown_tool(name='a')", "unknown function"), ("mesh_sdf", "tool function"), ("f = mesh_sdf", "tool function"),
                                 ("", "empty")):
            result, _ = run(source)
            self.assertFalse(result.ok, source)
            self.assertIn(fragment, result.error, source)

    def test_positional_arguments_are_refused_with_a_hint(self):
        result, _ = run('object_create("A", "CUBE")')
        self.assertFalse(result.ok)
        self.assertIn("keyword arguments", result.error)

    def test_validate_script_alone(self):
        validate_script('mesh_sdf(name="A", shapes=[])', [function_name(t) for t in TOOLS])
        with self.assertRaises(ScriptError) as ctx:
            validate_script("import os", [])
        self.assertIn("import", str(ctx.exception))
        self.assertEqual(ctx.exception.line, 1)


class TestSandbox(unittest.TestCase):

    def assertBlocked(self, source, fragment=None):
        result, rec = run(source)
        self.assertFalse(result.ok, source)
        self.assertEqual(rec.calls, [], source)                    # kuch bhi chala nahi
        if fragment:
            self.assertIn(fragment, result.error, source)

    def test_imports_attributes_builtins_and_dunders(self):
        for source in ("import os", "from os import system", "x = (1).__class__", "x = ().__class__.__bases__[0]", "x = 'a'.upper()",
                       "open('f')", "eval('1')", "exec('1')", "__import__('os')", "getattr(x, 'a')", "print(1)", "input()", "type(1)",
                       "vars()", "dir()", "globals()", "compile('1','a','exec')", "x = _a", "_a = 1", "y = object", "z = __builtins__",
                       "f = lambda: 1", "class A: pass", "x = [i for i in range(3) if i.real]", "s = f'{x.y}'", "x = f'{().__class__}'"):
            self.assertBlocked(source)

    def test_forbidden_statements(self):
        for source in ("while True:\n    pass", "try:\n    pass\nexcept:\n    pass", "with a:\n    pass", "global g", "del x", "assert 1",
                       "raise ValueError", "async def f(): pass", "x: int = 1", "for i in range(3):\n    pass\nelse:\n    pass",
                       "def f(*a): pass", "def f(**k): pass", "@d\ndef f(): pass", "def f(a: int): pass", "return 1", "x = {1, 2}",
                       "x = {k: 1 for k in [1]}", "x = (i for i in [1])", "x = ~1", "x = 1 & 2", "x = 1 << 3", "x = [*a]", "if (n := 1): pass",
                       "match x:\n    case 1: pass"):
            self.assertBlocked(source)

    def test_tool_names_are_protected_but_ordinary_variable_names_are_free(self):
        for source in ("mesh_sdf = 1", "def mesh_sdf(): pass", "for object_create in [1]: pass", "def f(object_create): pass"):
            self.assertBlocked(source, "tool function name")
        # LLM aksar `log`, `max`, `list`, `pi`... ko variable bana deta hai: chalna chahiye
        source = """
log = object_create(name="Log", primitive="CYLINDER")
max = 3
list = [1, 2]
pi = 3.14
def f(sin):
    return sin + max
note("hello")
object_create(name=str(f(1) + list[0] + pi), primitive="CUBE")
"""
        result, rec = run(source)
        self.assertTrue(result.ok, result.error)
        self.assertEqual([c[1]["name"] for c in rec.calls], ["Log", "8.14"])

    def test_note_and_log_leave_comments(self):
        result, _ = run('note("building the roof")\nlog("and the door")')
        self.assertTrue(result.ok, result.error)
        self.assertEqual(result.log, ["building the roof", "and the door"])

    def test_resource_limits(self):
        limited = ScriptLimits(max_tool_calls=5, max_ticks=1000, max_range=50)
        for source, fragment in (("for i in range(100):\n    pass", "range() is too large"),
                                 ("for i in range(50):\n    for j in range(50):\n        for k in range(50):\n            pass", "too many loop rounds"),
                                 ("for i in range(10):\n    object_create(name='a', primitive='CUBE')", "too many tool calls"),
                                 ("def f():\n    f()\nf()", "recursion"), ("x = [0] * 10000000", "repeating"), ("y = 'ab' * 999999", "repeating"),
                                 ("z = 10 ** 300", "exponent"), ("z = 9 ** 99999", "exponent"), ("z = 99999999 ** 60", "too large")):
            result, rec = run(source, limits=limited)
            self.assertFalse(result.ok, source)
            self.assertIn(fragment, result.error, source)
        ok, _ = run("x = [0] * 1000\ny = 2 ** 10\ny *= 3\ny **= 2", limits=limited)
        self.assertTrue(ok.ok, ok.error)

    def test_time_limit(self):
        clock = iter(range(0, 10_000, 100))
        result = run_script("for i in range(500):\n    pass", Recorder(), TOOLS, ScriptLimits(max_seconds=5.0), clock=lambda: next(clock))
        self.assertFalse(result.ok)
        self.assertIn("longer than", result.error)

    def test_namespace_has_no_escape_routes(self):
        captured = {}

        def spy(tool, kwargs):
            captured.update(kwargs)
            return Reply(True, {})
        run_script("object_create(name='a', primitive='CUBE')", spy, TOOLS)
        self.assertEqual(captured, {"name": "a", "primitive": "CUBE"})
        # tool functions only see plain data; script cannot reach call_tool, the result object or the namespace
        for source in ("x = object_create.__globals__", "x = object_create.__closure__", "x = range.__self__"):
            result, _ = run(source)
            self.assertFalse(result.ok, source)

    def test_parser_errors_of_every_python_version_are_handled(self):
        """Python 3.10 ast.parse null byte par ValueError deta hai (3.12 SyntaxError); gehra nesting RecursionError/MemoryError."""
        import ast
        from unittest import mock
        for error, fragment in ((ValueError("source code string cannot contain null bytes"), "invalid characters"),
                                (RecursionError("maximum recursion depth exceeded"), "nested too deeply"), (MemoryError(), "nested too deeply")):
            with mock.patch.object(ast, "parse", side_effect=error):
                result, rec = run("x = 1")
            self.assertFalse(result.ok)
            self.assertIn(fragment, result.error)
            self.assertEqual(rec.calls, [])
        with self.assertRaises(ScriptError):
            validate_script("a = 1\x00", [])

    def test_the_run_never_raises_even_for_hostile_input(self):
        for source in ("x = " + "(" * 500 + "1" + ")" * 500, "a" * 30000, "x = 1\n" * 9000, "\x00", "for i in range(3):\n" + "    " * 300 + "pass"):
            result, _ = run(source)
            self.assertFalse(result.ok and "\x00" in source)


if __name__ == "__main__":
    unittest.main()