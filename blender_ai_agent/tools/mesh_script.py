"""
mesh_script.py
===============
Hinglish: Jab koi request engine ke operators se na bane, to LLM ek chhota formula likh sakta hai jo HAR vertex par chalta
hai ("sirf pure math") — isse koi bhi deformation ban sakti hai. Ye `python.execute` jaisa khatarnak nahi: yahan bpy hai hi nahi,
sirf math, aur code pehle AST se jaanch kar chalta hai (import / attribute / dunder / while / function / list sab BAND).

Script ke andar ye naam milte hain (sirf padhne ke liye):
   x y z          vertex ka world position            u v w          bounding box ke andar 0..1 position
   nx ny nz       vertex normal                        i n            vertex ka index, kul vertices
   size           object ka sabse bada naap            cx cy cz       center
   minx..maxz     bounding box
Script ye set karta hai:
   dx dy dz       displacement (default 0)             remove         1 kar do to us vertex wale faces hat jaayenge
   (ya seedha x, y, z ko naya value de do)
Functions: sin cos tan asin acos atan atan2 sqrt exp log hypot floor ceil abs min max pow radians degrees sign clamp lerp
           smoothstep step fract mod noise fbm ridged rand      Constants: pi tau e
Control: if / elif / else, for k in range(<=32 literal), =, +=, -=, *=, /=

Example (twist-and-flare):   a = (w - 0.5) * 3.0
                              dx = (x - cx) * (cos(a) - 1) - (y - cy) * sin(a)
                              dy = (x - cx) * sin(a) + (y - cy) * (cos(a) - 1)
"""

import ast
import math
import time
from typing import Any, Callable, Dict, List, Sequence, Set, Tuple

from .mesh_engine import MeshInfo, OpResult, clamp, selection_weights, smoothstep
from .mesh_noise import fbm, rand01, ridged, value_noise


class ScriptError(ValueError):
    """Script galat / khatarnak / bahut dheemi."""


MAX_SOURCE = 4000
MAX_NODES = 900
MAX_LOOP_ITERATIONS = 64
MAX_POW = 8

INPUT_NAMES = ("x", "y", "z", "u", "v", "w", "nx", "ny", "nz", "i", "n", "size", "cx", "cy", "cz",
               "minx", "miny", "minz", "maxx", "maxy", "maxz")
OUTPUT_NAMES = ("dx", "dy", "dz", "remove")


def _sign(a): return (a > 0) - (a < 0)
def _lerp(a, b, t): return a + (b - a) * t
def _step(edge, x): return 1.0 if x >= edge else 0.0
def _fract(x): return x - math.floor(x)
def _mod(a, b): return a % b if b else 0.0
def _noise(x, y, z): return value_noise(x, y, z, 0)
def _fbm(x, y, z, octaves=3): return fbm(x, y, z, int(octaves), seed=0)
def _ridged(x, y, z, octaves=3): return ridged(x, y, z, int(octaves), seed=0)
def _rand(index): return rand01(int(index), 0)


ALLOWED_FUNCS: Dict[str, Callable] = {
    "sin": math.sin, "cos": math.cos, "tan": math.tan, "asin": math.asin, "acos": math.acos, "atan": math.atan,
    "atan2": math.atan2, "sqrt": math.sqrt, "exp": math.exp, "log": math.log, "hypot": math.hypot, "floor": math.floor,
    "ceil": math.ceil, "abs": abs, "min": min, "max": max, "pow": math.pow, "radians": math.radians,
    "degrees": math.degrees, "sign": _sign, "clamp": clamp, "lerp": _lerp, "smoothstep": smoothstep, "step": _step,
    "fract": _fract, "mod": _mod, "noise": _noise, "fbm": _fbm, "ridged": _ridged, "rand": _rand,
}
ALLOWED_CONSTANTS = {"pi": math.pi, "tau": math.tau, "e": math.e}

_ALLOWED_BINOPS = (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Mod, ast.Pow, ast.FloorDiv)
_ALLOWED_UNARY = (ast.UAdd, ast.USub, ast.Not)
_ALLOWED_CMP = (ast.Lt, ast.Gt, ast.LtE, ast.GtE, ast.Eq, ast.NotEq)


class _Validator(ast.NodeVisitor):
    def __init__(self, assigned: Set[str]):
        self.assigned = assigned
        self.nodes = 0
        self.loop_stack: List[int] = []

    def generic_visit(self, node):
        self.nodes += 1
        if self.nodes > MAX_NODES:
            raise ScriptError("script is too long/complex")
        super().generic_visit(node)

    def _fail(self, node, why):
        raise ScriptError(f"not allowed: {why} (line {getattr(node, 'lineno', '?')})")

    # ---- statements ----
    def visit_Module(self, node):
        for stmt in node.body:
            self.visit(stmt)

    def visit_Assign(self, node):
        for target in node.targets:
            if not isinstance(target, ast.Name):
                self._fail(node, "assign only to plain names")
            self._check_store(target)
        self.visit(node.value)

    def visit_AugAssign(self, node):
        if not isinstance(node.target, ast.Name) or not isinstance(node.op, _ALLOWED_BINOPS):
            self._fail(node, "unsupported augmented assignment")
        self._check_store(node.target)
        self.visit(node.value)

    def visit_If(self, node):
        self.visit(node.test)
        for stmt in node.body + node.orelse:
            self.visit(stmt)

    def visit_For(self, node):
        if not isinstance(node.target, ast.Name) or node.orelse:
            self._fail(node, "use: for k in range(<number>):")
        self._check_store(node.target)
        call = node.iter
        if not (isinstance(call, ast.Call) and isinstance(call.func, ast.Name) and call.func.id == "range"
                and 1 <= len(call.args) <= 2 and not call.keywords
                and all(isinstance(a, ast.Constant) and isinstance(a.value, int) and not isinstance(a.value, bool) for a in call.args)):
            self._fail(node, "loops must be `for k in range(<whole number literal>)`")
        values = [a.value for a in call.args]
        count = values[0] if len(values) == 1 else values[1] - values[0]
        if count < 0 or count > 32:
            self._fail(node, "a loop may run at most 32 times")
        total = count
        for outer in self.loop_stack:
            total *= max(outer, 1)
        if total > MAX_LOOP_ITERATIONS:
            self._fail(node, f"nested loops may run at most {MAX_LOOP_ITERATIONS} iterations in total")
        self.loop_stack.append(count)
        for stmt in node.body:
            self.visit(stmt)
        self.loop_stack.pop()

    def visit_Pass(self, node):
        pass

    # ---- expressions ----
    def visit_BinOp(self, node):
        if not isinstance(node.op, _ALLOWED_BINOPS):
            self._fail(node, "operator")
        if isinstance(node.op, ast.Pow):
            right = node.right
            if isinstance(right, ast.UnaryOp) and isinstance(right.op, (ast.USub, ast.UAdd)):
                right = right.operand                       # -2 jaisa negative literal bhi chalega
            if not (isinstance(right, ast.Constant) and isinstance(right.value, (int, float)) and abs(right.value) <= MAX_POW):
                self._fail(node, f"`**` needs a literal exponent between -{MAX_POW} and {MAX_POW} (or use pow())")
        self.visit(node.left)
        self.visit(node.right)

    def visit_UnaryOp(self, node):
        if not isinstance(node.op, _ALLOWED_UNARY):
            self._fail(node, "operator")
        self.visit(node.operand)

    def visit_BoolOp(self, node):
        for value in node.values:
            self.visit(value)

    def visit_Compare(self, node):
        if not all(isinstance(op, _ALLOWED_CMP) for op in node.ops):
            self._fail(node, "comparison")
        self.visit(node.left)
        for comparator in node.comparators:
            self.visit(comparator)

    def visit_IfExp(self, node):
        self.visit(node.test)
        self.visit(node.body)
        self.visit(node.orelse)

    def visit_Call(self, node):
        if not isinstance(node.func, ast.Name) or node.func.id not in ALLOWED_FUNCS:
            self._fail(node, "only these functions are available: " + ", ".join(sorted(ALLOWED_FUNCS)))
        if node.keywords or len(node.args) > 6 or any(isinstance(a, ast.Starred) for a in node.args):
            self._fail(node, "plain positional arguments only")
        for arg in node.args:
            self.visit(arg)

    def visit_Name(self, node):
        if node.id.startswith("_"):
            self._fail(node, "names starting with _")
        if isinstance(node.ctx, ast.Load):
            if node.id in ALLOWED_FUNCS:
                self._fail(node, f"`{node.id}` is a function - call it like {node.id}(...)")
            if not (node.id in INPUT_NAMES or node.id in OUTPUT_NAMES or node.id in ALLOWED_CONSTANTS or node.id in self.assigned):
                self._fail(node, f"unknown name '{node.id}'")

    def visit_Constant(self, node):
        if not isinstance(node.value, (int, float, bool)):
            self._fail(node, "only numbers are allowed")

    def _check_store(self, target):
        if target.id.startswith("_") or target.id in ALLOWED_FUNCS or target.id in ALLOWED_CONSTANTS:
            self._fail(target, f"cannot assign to '{target.id}'")

    def visit_Expr(self, node):
        self._fail(node, "a bare expression does nothing; assign to dx/dy/dz instead")

    def generic_unsupported(self, node):
        self._fail(node, type(node).__name__)


# Jo node types visit_* se handle nahi hue unhe reject karne ke liye default
for _name in ("Attribute", "Subscript", "Lambda", "ListComp", "SetComp", "DictComp", "GeneratorExp", "Import", "ImportFrom",
              "While", "FunctionDef", "AsyncFunctionDef", "ClassDef", "Global", "Nonlocal", "Try", "With", "Delete", "Raise",
              "Assert", "Return", "Starred", "JoinedStr", "FormattedValue", "Dict", "List", "Set", "Tuple", "Await", "Yield",
              "YieldFrom", "NamedExpr", "Match", "Break", "Continue", "AnnAssign"):
    if hasattr(ast, _name):
        setattr(_Validator, f"visit_{_name}", _Validator.generic_unsupported)


def compile_script(source: str) -> Callable:
    """Source ko jaanch kar ek safe function (x, y, z, ... ) -> (nx, ny, nz, remove) mein badalta hai."""
    if not isinstance(source, str) or not source.strip():
        raise ScriptError("script is empty")
    if len(source) > MAX_SOURCE:
        raise ScriptError(f"script is too long (max {MAX_SOURCE} characters)")
    try:
        tree = ast.parse(source.replace("\r\n", "\n"), mode="exec")
    except SyntaxError as exc:
        raise ScriptError(f"syntax error: {exc.msg} (line {exc.lineno})") from exc

    assigned = {t.id for n in ast.walk(tree) for t in
                (n.targets if isinstance(n, ast.Assign) else [n.target] if isinstance(n, (ast.AugAssign, ast.For)) else [])
                if isinstance(t, ast.Name)}
    _Validator(assigned).visit(tree)

    prelude = ast.parse("dx = 0.0\ndy = 0.0\ndz = 0.0\nremove = 0.0").body
    result = ast.Return(value=ast.parse("(x + dx, y + dy, z + dz, remove)", mode="eval").body)
    arguments = ast.arguments(posonlyargs=[], args=[ast.arg(arg=name) for name in INPUT_NAMES], vararg=None,
                              kwonlyargs=[], kw_defaults=[], kwarg=None, defaults=[])
    function = ast.FunctionDef(name="_vertex", args=arguments, body=prelude + tree.body + [result], decorator_list=[], returns=None)
    if "type_params" in ast.FunctionDef._fields:
        function.type_params = []
    module = ast.Module(body=[function], type_ignores=[])
    ast.fix_missing_locations(module)

    namespace: Dict[str, Any] = {"__builtins__": {}}
    namespace.update(ALLOWED_FUNCS)
    namespace.update(ALLOWED_CONSTANTS)
    namespace["range"] = range            # sirf `for k in range(<literal>)` ke liye (validator baaki jagah range() call rokta hai)
    exec(compile(module, "<mesh_script>", "exec"), namespace)  # noqa: S102 — AST pehle jaanch li gayi hai
    return namespace["_vertex"]


def run_script(info: MeshInfo, source: str, select: Any = None, seed: int = 1, time_limit: float = 8.0) -> OpResult:
    """Script ko (selection ke weight ke saath) har vertex par chalata hai. OpResult deta hai (moves + remove_faces)."""
    function = compile_script(source)
    n = len(info.vertices)
    if n > 200_000:
        raise ScriptError("mesh is too large for a script (max 200,000 vertices)")
    weights = selection_weights(select, info, seed)
    mins, maxs, ext, centre = info.mins, info.maxs, info.extent, info.center

    def unit(value, k):
        return (value - mins[k]) / ext[k] if ext[k] > 1e-12 else 0.5

    moves: Dict[int, Tuple[float, float, float]] = {}
    removed_vertices: Set[int] = set()
    errors = 0
    started = time.monotonic()
    for i, (x, y, z) in enumerate(info.vertices):
        w = weights[i]
        if w <= 1e-6:
            continue
        if (i & 255) == 0 and time.monotonic() - started > time_limit:
            raise ScriptError(f"the script is too slow (more than {time_limit:.0f}s); simplify it")
        nx, ny, nz = info.normals[i]
        try:
            qx, qy, qz, remove = function(x, y, z, unit(x, 0), unit(y, 1), unit(z, 2), nx, ny, nz, i, n, info.size,
                                          centre[0], centre[1], centre[2], mins[0], mins[1], mins[2], maxs[0], maxs[1], maxs[2])
        except (ArithmeticError, ValueError):
            errors += 1
            continue
        if not all(math.isfinite(c) for c in (qx, qy, qz, remove)):
            errors += 1
            continue
        if remove > 0.5 and w > 0.5:
            removed_vertices.add(i)
        q = (x + (qx - x) * w, y + (qy - y) * w, z + (qz - z) * w)
        if q != (x, y, z):
            moves[i] = q
    if errors > max(10, n * 0.05):
        raise ScriptError(f"the script failed (math error) on {errors} vertices; check divisions by zero / sqrt of negatives")

    remove_faces = [fi for fi, f in enumerate(info.faces) if any(v in removed_vertices for v in f)] if removed_vertices else []
    note = f"script moved {len(moves)} vertices" + (f", removed {len(remove_faces)} faces" if remove_faces else "")
    if errors:
        note += f" ({errors} vertices skipped by math errors)"
    return OpResult(moves, remove_faces, note, affected=sum(1 for x in weights if x > 1e-6))