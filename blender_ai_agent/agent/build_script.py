"""
build_script.py
================
Hinglish: Gemini (ya koi bhi LLM) jo "build script" likhta hai use SAFE tareeke se chalane ka engine.

Script Python ka ek chhota hissa (subset) hai jo sirf hamare TOOLS ko keyword arguments ke saath bula sakta hai:

    r = mesh_sdf(name="Body", resolution=60, shapes=[...])
    for i in range(4):
        object_create(name=f"Wheel{i}", primitive="CYLINDER", location=[1.3 * (i % 2 * 2 - 1), 0.8, 0.35])
    material_assign(object_name=r["name"], material_name="Paint")

Chalne se pehle script AST se jaanchi jaati hai: import, attribute (x.y), while, lambda, class, try, open/eval/exec, dunder, `*args`,
global — sab BAND. Loop / function / list-comprehension / f-string / math chalte hain. Har loop-round, function-call, tool-call
ginta hai (limit), seq-repeat aur power ka size check hota hai, aur kul samay ki seema hai. bpy script ko milta hi nahi.
"""

import ast
import math
import sys
import time
import traceback
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, List, Optional, Set


class ScriptError(ValueError):
    def __init__(self, message: str, line: Optional[int] = None):
        super().__init__(message)
        self.line = line

    def __str__(self) -> str:
        base = super().__str__()
        return f"line {self.line}: {base}" if self.line else base


class ScriptToolError(ScriptError):
    """Script ne koi tool bulaya aur tool fail hua."""

    def __init__(self, tool: str, message: str, line: Optional[int] = None):
        super().__init__(f"{tool} failed: {message}", line)
        self.tool = tool
        self.tool_message = message


@dataclass
class ScriptLimits:
    max_tool_calls: int = 400
    max_seconds: float = 240.0
    max_ticks: int = 200_000          # loop-rounds + function-calls ka kul
    max_range: int = 2000
    max_source: int = 24_000
    max_nodes: int = 8_000
    max_log: int = 60


def function_name(tool_name: str) -> str:
    """'mesh.sdf' -> 'mesh_sdf'"""
    return tool_name.replace(".", "_").replace("-", "_")


def _clamp(x, lo=0.0, hi=1.0):
    return lo if x < lo else hi if x > hi else x


def _lerp(a, b, t):
    return a + (b - a) * t


def _rand(i, seed=0):
    h = (int(i) * 374761393 + int(seed) * 668265263) & 0xFFFFFFFF
    h = ((h ^ (h >> 13)) * 1274126177) & 0xFFFFFFFF
    return (h ^ (h >> 16)) / 4294967296.0


MATH_NAMES = {
    "sin": math.sin, "cos": math.cos, "tan": math.tan, "asin": math.asin, "acos": math.acos, "atan": math.atan, "atan2": math.atan2,
    "sqrt": math.sqrt, "exp": math.exp, "log10": math.log10, "hypot": math.hypot, "floor": math.floor, "ceil": math.ceil,
    "radians": math.radians, "degrees": math.degrees, "pi": math.pi, "tau": math.tau, "clamp": _clamp, "lerp": _lerp, "rand": _rand,
}
SAFE_BUILTINS = {
    "abs": abs, "min": min, "max": max, "round": round, "sum": sum, "len": len, "enumerate": enumerate, "zip": zip, "int": int,
    "float": float, "str": str, "bool": bool, "list": list, "tuple": tuple, "dict": dict, "sorted": sorted, "reversed": reversed,
    "any": any, "all": all, "True": True, "False": False, "None": None,
}
RESERVED = set(MATH_NAMES) | set(SAFE_BUILTINS) | {"range", "log", "note"}

_ALLOWED_NODES = (
    ast.Module, ast.Assign, ast.AugAssign, ast.For, ast.If, ast.Expr, ast.Pass, ast.Break, ast.Continue, ast.FunctionDef, ast.Return,
    ast.arguments, ast.arg, ast.BoolOp, ast.BinOp, ast.UnaryOp, ast.Compare, ast.IfExp, ast.Call, ast.keyword, ast.Name, ast.Constant,
    ast.List, ast.Tuple, ast.Dict, ast.Subscript, ast.Slice, ast.ListComp, ast.comprehension, ast.JoinedStr, ast.FormattedValue,
    ast.Load, ast.Store,
    ast.And, ast.Or, ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod, ast.Pow, ast.USub, ast.UAdd, ast.Not,
    ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE, ast.In, ast.NotIn, ast.Is, ast.IsNot,
)
_FRIENDLY = {
    "Import": "import", "ImportFrom": "import", "While": "while loops (use `for i in range(n)`)", "Lambda": "lambda", "ClassDef": "class",
    "Try": "try/except", "With": "with", "Raise": "raise", "Assert": "assert", "Global": "global", "Nonlocal": "nonlocal",
    "Delete": "del", "AsyncFunctionDef": "async", "Await": "await", "Yield": "yield", "YieldFrom": "yield", "Attribute": "attribute access (`x.y`)",
    "Starred": "`*args` unpacking", "SetComp": "set comprehension", "DictComp": "dict comprehension", "GeneratorExp": "generator expression",
    "Set": "set literal", "NamedExpr": "`:=`", "AnnAssign": "annotated assignment", "Match": "match", "BitAnd": "bit operators",
    "BitOr": "bit operators", "BitXor": "bit operators", "LShift": "shift", "RShift": "shift", "MatMult": "`@`", "Invert": "`~`",
}


class _Validator:
    def __init__(self, source: str, tool_functions: Set[str], limits: ScriptLimits):
        self.source = source
        self.tools = set(tool_functions)
        self.limits = limits
        self.defined: Set[str] = set()

    def fail(self, node: Optional[ast.AST], message: str):
        raise ScriptError(message, getattr(node, "lineno", None))

    def check(self) -> ast.Module:
        if not isinstance(self.source, str) or not self.source.strip():
            raise ScriptError("the script is empty")
        if len(self.source) > self.limits.max_source:
            raise ScriptError(f"the script is too long (max {self.limits.max_source} characters)")
        try:
            tree = ast.parse(self.source.replace("\r\n", "\n"), mode="exec")
        except SyntaxError as exc:
            raise ScriptError(f"syntax error: {exc.msg}", exc.lineno) from exc
        except ValueError as exc:                                  # Python 3.10: null byte / kharab text
            raise ScriptError(f"the script contains invalid characters ({exc})") from exc
        except (RecursionError, MemoryError) as exc:               # bahut gehra nesting
            raise ScriptError("the script is nested too deeply") from exc

        nodes = list(ast.walk(tree))
        if len(nodes) > self.limits.max_nodes:
            raise ScriptError("the script is too complex")
        for node in nodes:
            if not isinstance(node, _ALLOWED_NODES):
                name = type(node).__name__
                self.fail(node, f"not allowed: {_FRIENDLY.get(name, name)}")

        # naam jo script khud define karti hai
        for node in nodes:
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
                self.define(node, node.id)
            elif isinstance(node, ast.FunctionDef):
                self.define(node, node.name)
                if node.decorator_list or node.returns is not None:
                    self.fail(node, "decorators / return annotations are not allowed")
                a = node.args
                if a.vararg or a.kwarg or a.kwonlyargs or a.posonlyargs:
                    self.fail(node, "functions take plain positional parameters only")
                for arg in a.args:
                    if arg.annotation is not None:
                        self.fail(node, "type annotations are not allowed")
                    self.define(node, arg.arg)
        self.call_targets = {id(n.func) for n in nodes if isinstance(n, ast.Call)}
        for node in nodes:
            self.check_node(node)
        self.check_returns(tree, in_function=False)
        return tree

    def define(self, node, name: str):
        if name.startswith("_"):
            self.fail(node, f"names starting with _ are not allowed ('{name}')")
        if name in self.tools:
            self.fail(node, f"'{name}' is a tool function name and cannot be reused as a variable")
        self.defined.add(name)

    def check_node(self, node):
        if isinstance(node, ast.Name):
            if node.id.startswith("_"):
                self.fail(node, f"names starting with _ are not allowed ('{node.id}')")
            if isinstance(node.ctx, ast.Load) and not (node.id in self.defined or node.id in RESERVED or node.id in self.tools):
                self.fail(node, f"unknown name '{node.id}'" + (" (tool functions are called like mesh_sdf(name=..., ...))" if "_" in node.id else ""))
            if isinstance(node.ctx, ast.Load) and node.id in self.tools and id(node) not in self.call_targets:
                self.fail(node, f"'{node.id}' is a tool function: call it like {node.id}(name=..., ...)")
        elif isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name):
                self.fail(node, "only plain function calls like name(...) are allowed")
            name = node.func.id
            if name not in self.tools and name not in RESERVED and name not in self.defined:
                self.fail(node, f"unknown function '{name}'" + ("" if name not in ("print", "open", "eval", "exec", "input", "getattr", "type", "vars", "dir")
                                                                else " (not available)"))
            for kw in node.keywords:
                if kw.arg is not None and kw.arg.startswith("_"):
                    self.fail(node, "keyword names starting with _ are not allowed")
        elif isinstance(node, ast.Constant):
            if not isinstance(node.value, (int, float, str, bool, type(None))):
                self.fail(node, "only numbers, strings, True/False/None are allowed as literals")
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                self.check_target(node, target)
        elif isinstance(node, ast.AugAssign):
            self.check_target(node, node.target)
        elif isinstance(node, ast.For):
            self.check_target(node, node.target, loop=True)
            if node.orelse:
                self.fail(node, "for/else is not allowed")
        elif isinstance(node, ast.comprehension):
            self.check_target(node, node.target, loop=True)

    def check_target(self, node, target, loop: bool = False):
        """Name, ya Name/tuple ka (nested bhi) unpacking: `a, (b, c) = ...`; `for i, (x, y) in enumerate(...)`. Subscript sirf assign mein."""
        if isinstance(target, ast.Name):
            return
        if isinstance(target, ast.Tuple) and target.elts:
            for element in target.elts:
                self.check_target(node, element, loop)
            return
        if not loop and isinstance(target, ast.Subscript) and isinstance(target.value, ast.Name):
            return
        self.fail(node, "assign to a plain name (or `name[index]`, or a tuple of names)")

    def check_returns(self, tree: ast.AST, in_function: bool):
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.Return) and not in_function:
                self.fail(node, "`return` is only allowed inside a function")
            self.check_returns(node, in_function or isinstance(node, ast.FunctionDef))


class _Instrument(ast.NodeTransformer):
    """Har loop-round / function-entry par _tick(); `*` aur `**` ko size-checked helper se badalta hai."""

    @staticmethod
    def _call(name: str, args: List[ast.expr]) -> ast.Call:
        return ast.Call(func=ast.Name(id=name, ctx=ast.Load()), args=args, keywords=[])

    def _tick_stmt(self) -> ast.stmt:
        return ast.Expr(value=self._call("_tick", []))

    def _tick_for(self, body: List[ast.stmt]) -> ast.stmt:
        stmt = self._tick_stmt()
        return ast.copy_location(stmt, body[0]) if body else stmt        # error ki line = body ki pehli line

    def visit_For(self, node: ast.For):
        self.generic_visit(node)
        node.body = [self._tick_for(node.body)] + node.body
        return node

    def visit_FunctionDef(self, node: ast.FunctionDef):
        self.generic_visit(node)
        node.body = [self._tick_for(node.body)] + node.body
        return node

    def visit_BinOp(self, node: ast.BinOp):
        self.generic_visit(node)
        if isinstance(node.op, ast.Mult):
            return ast.copy_location(self._call("_mul", [node.left, node.right]), node)
        if isinstance(node.op, ast.Pow):
            return ast.copy_location(self._call("_pow", [node.left, node.right]), node)
        return node

    def visit_AugAssign(self, node: ast.AugAssign):
        self.generic_visit(node)
        if isinstance(node.op, (ast.Mult, ast.Pow)):
            load = ast.parse(ast.unparse(node.target), mode="eval").body
            helper = "_mul" if isinstance(node.op, ast.Mult) else "_pow"
            return ast.copy_location(ast.Assign(targets=[node.target], value=self._call(helper, [load, node.value])), node)
        return node


def validate_script(source: str, tool_functions: Iterable[str], limits: Optional[ScriptLimits] = None) -> None:
    """Script jaanch lo (chalaye bina). Galat ho to ScriptError (line number ke saath)."""
    _Validator(source, set(tool_functions), limits or ScriptLimits()).check()


@dataclass
class RunResult:
    ok: bool
    error: Optional[str] = None
    error_line: Optional[int] = None
    calls: List[Dict[str, Any]] = field(default_factory=list)
    log: List[str] = field(default_factory=list)
    ticks: int = 0
    seconds: float = 0.0


def _preview(value: Any, limit: int = 90) -> str:
    text = repr(value)
    return text if len(text) <= limit else text[:limit] + "..."


def run_script(source: str, call_tool: Callable[[str, Dict[str, Any]], Any], tool_names: Iterable[str],
               limits: Optional[ScriptLimits] = None, clock: Callable[[], float] = time.monotonic) -> RunResult:
    """
    Script chalao. `call_tool(tool_name, kwargs)` ToolResult jaisa object deta hai (.success, .data, .error).
    Kabhi exception nahi uthata — natija RunResult mein (ok / error / error_line / kitne tool bulaye).
    """
    limits = limits or ScriptLimits()
    tool_names = list(tool_names)
    name_map = {function_name(t): t for t in tool_names}
    result = RunResult(ok=False)
    started = clock()

    try:
        validator = _Validator(source, set(name_map), limits)
        tree = validator.check()
    except ScriptError as exc:
        result.error, result.error_line = str(exc), exc.line
        return result

    state = {"ticks": 0, "calls": 0}

    def guard():
        if clock() - started > limits.max_seconds:
            raise ScriptError(f"the script ran longer than {limits.max_seconds:.0f}s")

    def tick():
        state["ticks"] += 1
        if state["ticks"] > limits.max_ticks:
            raise ScriptError("too many loop rounds / function calls")
        if (state["ticks"] & 255) == 0:
            guard()

    def safe_range(*args):
        r = range(*args)
        if len(r) > limits.max_range:
            raise ScriptError(f"range() is too large (max {limits.max_range})")
        return r

    def safe_mul(a, b):
        for seq, count in ((a, b), (b, a)):
            if isinstance(seq, (list, tuple, str)) and isinstance(count, int) and not isinstance(count, bool) and count > 100_000:
                raise ScriptError("repeating a list/string that many times is not allowed")
        return a * b

    def safe_pow(a, b):
        if isinstance(b, (int, float)) and abs(b) > 64:
            raise ScriptError("exponent too large (max 64)")
        if isinstance(a, int) and isinstance(b, int) and b > 0 and abs(a) > 1 and b * math.log2(abs(a)) > 256:
            raise ScriptError("number too large")
        return a ** b

    def log(message="", *rest):
        if len(result.log) < limits.max_log:
            result.log.append(str(message)[:200])

    def make_tool(fn_name: str, tool_name: str):
        def tool(*args, **kwargs):
            if args:
                raise ScriptError(f"{fn_name}(): use keyword arguments, e.g. {fn_name}(name=\"X\", ...)")
            state["calls"] += 1
            if state["calls"] > limits.max_tool_calls:
                raise ScriptError(f"too many tool calls (max {limits.max_tool_calls})")
            guard()
            reply = call_tool(tool_name, dict(kwargs))
            ok = bool(getattr(reply, "success", False))
            error = None if ok else str(getattr(reply, "error", "unknown error"))
            result.calls.append({"tool": tool_name, "ok": ok, "error": error, "args": _preview(kwargs)})
            if not ok:
                raise ScriptToolError(tool_name, error or "failed")
            data = getattr(reply, "data", None)
            return dict(data) if isinstance(data, dict) else {}
        tool.__name__ = fn_name
        return tool

    namespace: Dict[str, Any] = {"__builtins__": {}}
    namespace.update(SAFE_BUILTINS)
    namespace.update(MATH_NAMES)
    namespace.update({"range": safe_range, "log": log, "note": log, "_tick": tick, "_mul": safe_mul, "_pow": safe_pow})
    for fn_name, tool_name in name_map.items():
        namespace[fn_name] = make_tool(fn_name, tool_name)

    try:
        instrumented = _Instrument().visit(tree)
        ast.fix_missing_locations(instrumented)
        code = compile(instrumented, "<build_script>", "exec")
        exec(code, namespace)  # noqa: S102 — AST pehle jaanch li gayi hai, builtins khaali hain
        result.ok = True
    except ScriptError as exc:
        result.error, result.error_line = _locate(exc)
    except RecursionError:
        result.error, result.error_line = "recursion is too deep", _script_line()
    except ZeroDivisionError as exc:
        result.error, result.error_line = f"division by zero ({exc})", _script_line()
    except (TypeError, ValueError, KeyError, IndexError, NameError, AttributeError, OverflowError, MemoryError) as exc:
        result.error, result.error_line = f"{type(exc).__name__}: {exc}", _script_line()
    except SyntaxError as exc:
        result.error, result.error_line = f"syntax error: {exc.msg}", exc.lineno
    except Exception as exc:  # noqa: BLE001
        result.error, result.error_line = f"{type(exc).__name__}: {exc}", _script_line()
    result.ticks = state["ticks"]
    result.seconds = clock() - started
    if result.error and result.error_line and not result.error.startswith("line "):
        result.error = f"line {result.error_line}: {result.error}"
    return result


def _script_line() -> Optional[int]:
    """Traceback mein se script ki aakhri line."""
    frames = [f for f in traceback.extract_tb(sys.exc_info()[2]) if f.filename == "<build_script>"]
    return frames[-1].lineno if frames else None


def _locate(exc: ScriptError):
    return ValueError.__str__(exc), (exc.line or _script_line())