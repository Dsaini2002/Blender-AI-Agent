"""
post_verify.py  —  Har kaam ke BAAD apne aap: console + vision se check, galti ho to agent se theek karwana
=========================================================================================================
Hinglish: Controller ek request chalane se pehle `begin()` karta hai (scene ka snapshot + console capture shuru), chalne ke baad
`end()` (kya naya bana / kya badla + console ka text), phir `assess()`:

  1. CONSOLE   console text mein errors/warnings (shor hata kar) — "mesh not manifold", "StructRNA removed", Python errors...
  2. VISION    naya/badla hua 3 angle se render -> Gemini vision score + "kya galat hai" (sirf jab zaroori ho)
  3. needs_fix agar koi actionable console problem ya vision score < pass_score

needs_fix ho to controller `fix_prompt()` agent ko deta hai (max_rounds tak), phir dobara assess. Aakhir mein user ko saaf summary.
Settings: ~/BlenderAIAgent/autoverify.json  ya env BLENDER_AI_AUTOVERIFY=off|console|full  (GEMINI_API_KEY wahi jo addon use karta hai)
"""

import json
import os
import re
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

from . import self_correct as sc
from .console_watch import ConsoleCapture, Finding, analyze_console

RENDERABLE = {"MESH", "CURVE", "SURFACE", "META", "FONT", "CURVES", "POINTCLOUD", "VOLUME", "GPENCIL"}
MODES = ("off", "console", "full")


@dataclass
class VerifyConfig:
    mode: str = "full"                         # off | console (sirf console, free) | full (console + vision)
    max_rounds: int = 2                        # kitni baar agent se theek karwaye
    pass_score: float = 7.0
    views: Tuple[str, ...] = ("front", "right", "three_quarter")
    resolution: int = 512
    min_objects_for_vision: int = 3            # isse kam naye objects + simple request => vision nahi
    always_vision: bool = False
    fd_capture: bool = True
    output_dir: str = ""


def verify_config_path() -> str:
    env = os.environ.get("BLENDER_AI_AUTOVERIFY_CONFIG")
    return os.path.expanduser(env) if env else os.path.join(os.path.expanduser("~"), "BlenderAIAgent", "autoverify.json")


def load_verify_config(path: Optional[str] = None) -> VerifyConfig:
    cfg = VerifyConfig()
    try:
        with open(path or verify_config_path(), "r", encoding="utf-8") as handle:
            data = json.load(handle)
        if isinstance(data, dict):
            for key, value in data.items():
                if hasattr(cfg, key):
                    setattr(cfg, key, tuple(str(v) for v in value) if key == "views" and isinstance(value, list) else value)
    except (OSError, ValueError):
        pass
    env = os.environ.get("BLENDER_AI_AUTOVERIFY", "").strip().lower()
    if env in MODES:
        cfg.mode = env
    try:
        cfg.max_rounds = max(0, min(4, int(cfg.max_rounds)))
        cfg.pass_score = max(1.0, min(10.0, float(cfg.pass_score)))
        cfg.resolution = max(128, min(1024, int(cfg.resolution)))
        cfg.min_objects_for_vision = max(1, int(cfg.min_objects_for_vision))
    except (TypeError, ValueError):
        cfg = VerifyConfig(mode=cfg.mode if cfg.mode in MODES else "full")
    if cfg.mode not in MODES:
        cfg.mode = "full"
    return cfg


@dataclass
class RunFacts:
    created: List[str] = field(default_factory=list)
    changed: List[str] = field(default_factory=list)
    types: Dict[str, str] = field(default_factory=dict)
    console_text: str = ""
    console_mode: str = "none"
    started: float = 0.0


@dataclass
class CheckReport:
    round: int = 0
    findings: List[Finding] = field(default_factory=list)
    created: List[str] = field(default_factory=list)
    changed: List[str] = field(default_factory=list)
    score: Optional[float] = None
    summary: str = ""
    problems: List[Dict[str, str]] = field(default_factory=list)
    keep: List[str] = field(default_factory=list)
    images: List[str] = field(default_factory=list)
    vision_note: str = ""
    needs_fix: bool = False

    @property
    def actionable(self) -> List[Finding]:
        return [f for f in self.findings if f.actionable]


class RunSession:
    """Ek run ka snapshot + console capture. end() baar-baar bulane par bhi theek."""

    def __init__(self, verifier: "PostRunVerifier", request: str, baseline: Optional[Dict[str, str]] = None):
        self.verifier = verifier
        self.request = request
        self.before = verifier._records()
        self.baseline = baseline if baseline is not None else self.before
        self.started = time.time()
        self._capture: Optional[ConsoleCapture] = ConsoleCapture(fd_level=verifier.cfg.fd_capture)
        self._capture.__enter__()
        self._facts: Optional[RunFacts] = None

    def abort(self) -> None:
        if self._capture is not None:
            self._capture.__exit__(None, None, None)
            self._capture = None

    def end(self) -> RunFacts:
        if self._facts is not None:
            return self._facts
        text, mode = "", "none"
        if self._capture is not None:
            self._capture.__exit__(None, None, None)
            text, mode = self._capture.text(), self._capture.mode
            self._capture = None
        after = self.verifier._records()
        created = [n for n in after if n not in self.baseline]
        changed = [n for n in after if n in self.baseline and after[n] != self.baseline[n]]
        types = {n: self.verifier._types.get(n, "") for n in after}
        self._facts = RunFacts(created, changed, types, text, mode, self.started)
        return self._facts


class PostRunVerifier:
    def __init__(self, tool_caller: Any, bridge: Any, llm_factory: Optional[Callable[[sc.BuilderConfig], Any]] = None,
                 config_loader: Callable[[], VerifyConfig] = load_verify_config,
                 builder_config_loader: Callable[[], sc.BuilderConfig] = sc.load_builder_config):
        self.caller = tool_caller
        self.bridge = bridge
        self._llm_factory = llm_factory or (lambda cfg: sc.GeminiClient(cfg))
        self._config_loader = config_loader
        self._builder_loader = builder_config_loader
        self._types: Dict[str, str] = {}
        self._llm = None
        self._llm_key = None

    @property
    def cfg(self) -> VerifyConfig:
        return self._config_loader()

    @property
    def enabled(self) -> bool:
        return self.cfg.mode != "off"

    # ---------------------------------------------------------------- scene snapshot
    def _records(self) -> Dict[str, str]:
        """name -> signature (badlav pehchanne ke liye)."""
        from .models import ToolCall
        try:
            reply = self.caller.call(ToolCall(tool_name="scene.inspect", arguments={}))
        except Exception:  # noqa: BLE001
            return {}
        if not getattr(reply, "success", False) or not isinstance(reply.data, dict):
            return {}
        records: Dict[str, str] = {}
        self._types = {}
        for obj in reply.data.get("objects", []):
            name = str(obj.get("name", ""))
            if not name:
                continue
            self._types[name] = str(obj.get("type", ""))
            records[name] = json.dumps(obj, sort_keys=True, default=str)
        return records

    def begin(self, request: str, baseline: Optional[Dict[str, str]] = None) -> Optional[RunSession]:
        if not self.enabled:
            return None
        try:
            return RunSession(self, request, baseline)
        except Exception:  # noqa: BLE001 — check ki wajah se kaam kabhi na ruke
            return None

    # ---------------------------------------------------------------- assess
    def _vision_skip_reason(self, request: str, facts: RunFacts, targets: List[str], key: str) -> str:
        cfg = self.cfg
        if not targets:
            return "nothing new to look at"
        if any(t >= facts.started for t in sc.REVIEW_LOG):
            return "already reviewed by build.iterate"
        if not key:
            return "vision check skipped: no GEMINI_API_KEY"
        if not cfg.always_vision and len(facts.created) + len(facts.changed) < cfg.min_objects_for_vision:
            try:
                from ..tools.capability import assess_request
                if assess_request(request).verdict == "yes":
                    return "simple request: vision check not needed"
            except Exception:  # noqa: BLE001
                pass
        return ""

    def _llm_for(self, builder_cfg: sc.BuilderConfig):
        key = (builder_cfg.api_key, builder_cfg.model)
        if self._llm is None or self._llm_key != key:
            self._llm, self._llm_key = self._llm_factory(builder_cfg), key
        return self._llm

    def assess(self, request: str, facts: RunFacts, round_no: int = 0) -> CheckReport:
        cfg = self.cfg
        report = CheckReport(round=round_no, findings=analyze_console(facts.console_text), created=list(facts.created),
                             changed=list(facts.changed))
        if cfg.mode == "full":
            builder_cfg = self._builder_loader()
            targets = [n for n in facts.created + facts.changed if facts.types.get(n, "") in RENDERABLE]
            reason = self._vision_skip_reason(request, facts, targets, builder_cfg.api_key)
            if reason:
                report.vision_note = reason
            else:
                try:
                    folder = os.path.join(cfg.output_dir or os.path.join(os.path.expanduser("~"), "BlenderAIAgent", "checks"),
                                          time.strftime("%Y%m%d_%H%M%S") + f"_r{round_no}")
                    report.images = self.bridge.render_views(targets, list(cfg.views), cfg.resolution, folder, "check")
                    llm = self._llm_for(builder_cfg)
                    critique = sc.critique_renders(llm.generate, request, report.images)
                    if critique.raw_ok:
                        report.score, report.summary = critique.score, critique.summary
                        report.problems, report.keep = critique.problems, critique.keep
                    else:
                        report.vision_note = "the reviewer's answer could not be read"
                except sc.BuilderError as exc:
                    report.vision_note = f"vision check skipped: {exc.user_message}"
                except Exception as exc:  # noqa: BLE001 — render/image galti
                    report.vision_note = f"vision check skipped: {type(exc).__name__}: {exc}"
        serious = any(p.get("severity") in ("high", "medium") for p in report.problems)
        report.needs_fix = bool(report.actionable) or (report.score is not None and report.score < cfg.pass_score and serious)
        return report

    # ---------------------------------------------------------------- text for the agent / the user
    def fix_prompt(self, request: str, report: CheckReport, round_no: int) -> str:
        lines = [f"AUTOMATIC CHECK (round {round_no}): the work for the request below has problems found by looking at the Blender console "
                 "and at renders. Fix them with the tools - change, move, rebuild or delete only what is needed (never objects that existed "
                 "before this request). Do not start over unless a part is hopeless.",
                 f"Original request: {request}"]
        involved = (report.created + [n for n in report.changed if n not in report.created])[:20]
        if involved:
            lines.append("Objects involved: " + ", ".join(involved))
        if report.actionable:
            lines.append("Console problems:")
            lines += [f"- {f.line()}" for f in report.actionable[:6]]
        if report.score is not None and report.problems:
            lines.append(f"Visual review (score {report.score:g}/10): {report.summary}")
            lines += [f"- [{p['severity']}] {p['where']}: {p['issue']}" + (f" -> {p['fix']}" if p['fix'] else "") for p in report.problems[:6]]
            if report.keep:
                lines.append("Already right (keep): " + "; ".join(report.keep[:5]))
        lines.append("When done, reply with one short sentence about what you changed.")
        return "\n".join(lines)

    def announce(self, report: CheckReport, round_no: int) -> str:
        bits = []
        if report.actionable:
            bits.append(f"{len(report.actionable)} console problem(s)")
        if report.score is not None and report.needs_fix:
            bits.append(f"vision score {report.score:g}/10")
        return f"Auto-check ne dhunda: {' + '.join(bits) or 'kuch dikkat'} - theek kar raha hoon (round {round_no}/{self.cfg.max_rounds})."

    def format_history(self, history: List[CheckReport]) -> str:
        if not history:
            return ""
        first, last = history[0], history[-1]

        def state(r: CheckReport) -> str:
            parts = []
            parts.append("console clean" if not r.actionable else f"{len(r.actionable)} console problem(s)")
            if r.score is not None:
                parts.append(f"vision {r.score:g}/10")
            elif r.vision_note:
                parts.append(r.vision_note)
            return ", ".join(parts)

        if len(history) == 1:
            head = f"Auto-check ✓ ({state(first)})" if not first.needs_fix else f"Auto-check: problems remain ({state(first)})"
        elif not last.needs_fix:
            head = f"Auto-check ✓ fixed after {len(history) - 1} round(s): {state(first)}  ->  {state(last)}"
        else:
            head = f"Auto-check: {len(history) - 1} fix round(s) done, problems remain: {state(first)}  ->  {state(last)}"
        lines = [head]
        if last.needs_fix:
            lines += [f"  - {f.line()}" for f in last.actionable[:4]]
            lines += [f"  - [{p['severity']}] {p['where']}: {p['issue']}" for p in last.problems[:3]]
            lines.append("  (aur sudhaar chahiye to batao, ya dobara chalao)")
        notes = [r.vision_note for r in history if r.vision_note and r.score is None and "nothing new" not in r.vision_note
                 and "simple request" not in r.vision_note]
        if notes and not last.needs_fix:
            lines.append("  note: " + notes[-1])
        return "\n".join(lines)