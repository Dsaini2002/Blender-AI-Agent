
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
    mode: str = "full"
    # Check -> fix -> check again until the result passes. The loop also stops when the user presses Stop,
    # the Gemini quota is used up, `stall_rounds` rounds in a row bring no improvement, or after max_rounds
    # (a safety cap so a problem the agent cannot solve does not burn the whole daily quota).
    until_fixed: bool = True
    max_rounds: int = 15
    stall_rounds: int = 3
    # Precision review: the reviewer lists every expected element and every flaw (small ones too), and only a
    # flawless result scores 10. With strict_review every listed flaw is fixed, not only high / medium ones.
    strict_review: bool = True
    pass_score: float = 10.0
    views: Tuple[str, ...] = ("three_quarter", "front")
    # deep check: every side + top + low + zoomed out, and one zoomed-in close-up per checklist thing
    deep: bool = True
    closeups: int = 10
    resolution: int = 384
    min_objects_for_vision: int = 3
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
        cfg.max_rounds = max(0, min(30, int(cfg.max_rounds)))
        cfg.stall_rounds = max(1, min(10, int(cfg.stall_rounds)))
        cfg.until_fixed = bool(cfg.until_fixed)
        cfg.strict_review = bool(cfg.strict_review)
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
    geometry: List[Dict[str, str]] = field(default_factory=list)
    missing: List[str] = field(default_factory=list)
    needs_fix: bool = False
    folder: str = ""                       # checks/<time>_r<round>: the images, review.txt and fix_prompt.txt

    @property
    def actionable(self) -> List[Finding]:
        return [f for f in self.findings if f.actionable]


def review_text(report: "CheckReport", request: str = "") -> str:
    """What the automatic check saw and decided in one round - readable."""
    lines = [f"AUTOMATIC CHECK - round {report.round}   ({time.strftime('%Y-%m-%d %H:%M:%S')})", "=" * 90]
    if request:
        lines += ["REQUEST:", request.strip()[:3000], ""]
    lines.append("IMAGES the reviewer looked at:" if report.images else "IMAGES: none")
    lines += [f"  {os.path.basename(p)}" for p in report.images]
    lines.append("")
    lines.append("VISION REVIEW:")
    if report.score is not None:
        lines.append(f"  score: {report.score:g}/10")
        if report.summary:
            lines.append(f"  summary: {report.summary}")
        lines.append("  missing: " + (", ".join(report.missing) if report.missing else "nothing"))
        lines.append(f"  problems ({len(report.problems)}):")
        for p in report.problems:
            lines.append(f"    [{p.get('severity', '?')}] {p.get('where', '')}: {p.get('issue', '')}")
            if p.get("fix"):
                lines.append(f"        fix: {p.get('fix')}")
        if report.keep:
            lines.append("  keep (right as it is): " + ", ".join(report.keep))
    else:
        lines.append(f"  not done - {report.vision_note or 'vision is off'}")
    lines.append("")
    lines.append(f"GEOMETRY CHECK ({len(report.geometry)} problem(s)):")
    for p in report.geometry:
        lines.append(f"    [{p.get('severity', '?')}] {p.get('where', '')}: {p.get('issue', '')}")
        if p.get("fix"):
            lines.append(f"        fix: {p.get('fix')}")
    lines.append("")
    actionable = report.actionable
    lines.append(f"CONSOLE: {len(actionable)} error(s)" + ("" if actionable else " - clean"))
    for f in actionable[:10]:
        lines.append(f"    {getattr(f, 'kind', '')}: {getattr(f, 'message', '')}"[:300])
    lines.append("")
    lines.append("DECISION: " + ("fix needed - the problems above go to the agent as the next fix round "
                                "(see fix_prompt.txt in this folder)" if report.needs_fix else "no fix needed"))
    return "\n".join(lines) + "\n"


def write_review(report: "CheckReport", request: str = "") -> str:
    if not report.folder:
        return ""
    try:
        os.makedirs(report.folder, exist_ok=True)
        path = os.path.join(report.folder, "review.txt")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(review_text(report, request))
        return path
    except OSError:
        return ""


class RunSession:

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
    # A review is two small images: if the main model is this slow, the faster fallback model should get its turn.
    VISION_TIMEOUT_S = 75.0
    RETRY_WAIT_S = 8.0
    def __init__(self, tool_caller: Any, bridge: Any, llm_factory: Optional[Callable[[sc.BuilderConfig], Any]] = None,
                 config_loader: Callable[[], VerifyConfig] = load_verify_config,
                 builder_config_loader: Callable[[], sc.BuilderConfig] = sc.load_builder_config,
                 sleep: Callable[[float], None] = time.sleep):
        self.caller = tool_caller
        self.bridge = bridge
        self._sleep = sleep
        self._llm_factory = llm_factory or (lambda cfg: sc.make_vision_client(cfg))
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
        except Exception:  # noqa: BLE001 
            return None

    # ---------------------------------------------------------------- assess
    def _vision_skip_reason(self, request: str, facts: RunFacts, targets: List[str], key: str) -> str:
        cfg = self.cfg
        if not targets:
            return "nothing new to look at"
        if any(t >= facts.started for t in sc.REVIEW_LOG):
            return "already reviewed by build.iterate"
        if not key:
            return "vision check skipped: no GEMINI_API_KEY or ANTHROPIC_API_KEY"
        if not cfg.always_vision and len(facts.created) + len(facts.changed) < cfg.min_objects_for_vision:
            try:
                from ..tools.capability import assess_request
                if assess_request(request).verdict == "yes":
                    return "simple request: vision check not needed"
            except Exception:  # noqa: BLE001
                pass
        return ""

    def _llm_for(self, builder_cfg: sc.BuilderConfig):
        import dataclasses
        key = (builder_cfg.api_key, builder_cfg.model, getattr(builder_cfg, "vision_provider", ""))
        if self._llm is None or self._llm_key != key:
            cfg = builder_cfg
            if dataclasses.is_dataclass(cfg) and getattr(cfg, "request_timeout_s", 0) > self.VISION_TIMEOUT_S:
                cfg = dataclasses.replace(cfg, request_timeout_s=self.VISION_TIMEOUT_S)
            self._llm, self._llm_key = self._llm_factory(cfg), key
        return self._llm

    @staticmethod
    def _transient(exc: "sc.BuilderError") -> bool:
        """Gemini was slow or busy (timeout, 500, 503) - worth one more try. Quota (429) is not."""
        text = f"{exc} {getattr(exc, 'user_message', '')}"
        if "429" in text or "quota" in text.lower():
            return False
        return any(mark in text for mark in ("timeout", " 503", " 500", "did not answer", "cannot reach"))

    def _critique_with_retry(self, llm, request: str, images):
        try:
            return self._critique(llm, request, images)
        except sc.BuilderError as exc:
            if not self._transient(exc):
                raise
            self._sleep(self.RETRY_WAIT_S)
            return self._critique(llm, request, images)

    def _strict(self) -> bool:
        try:
            return bool(getattr(self.cfg, "strict_review", False))
        except Exception:  # noqa: BLE001
            return False

    RENDER_NOTE = ("These are automatic check renders. Roofs, ceilings and the walls nearest to the camera are hidden on "
                   "purpose so the inside can be seen - never report them as missing or broken. EACH view hides a "
                   "DIFFERENT wall: a thing that looks free-standing in one view may stand against the wall that view "
                   "hides - judge 'against the wall' from the views where that wall is visible and from the MEASURED "
                   "lines. Small items (a racket, "
                   "a shuttlecock, a cup) can be tiny in a wide view: look carefully before calling them missing. An image "
                   "named cutaway (the last one) shows a building with its outer walls, glass and doors hidden on purpose: "
                   "judge the rooms, furniture and halls inside from it - the walls are there in the other views.")

    def _critique(self, llm, request: str, images):
        extra = getattr(self, "_deep_inputs", None) or {}
        if self._strict():
            return sc.critique_renders(llm.generate, request, images, strict=True, note=self.RENDER_NOTE, **extra)
        return sc.critique_renders(llm.generate, request, images, note=self.RENDER_NOTE, **extra)

    def _deep_renders(self, request: str, facts, targets: List[str], folder: str) -> Tuple[List[str], dict]:
        """Every side + top + low + zoomed out, then one zoomed-in close-up per checklist thing; the checklist and
        the measured problems go to the reviewer with them."""
        from ..tools.render_views import DEEP_VIEWS
        cfg = self.cfg
        images = self.bridge.render_views(targets, list(DEEP_VIEWS), cfg.resolution, folder, "check")
        labels = {p: f"render view '{os.path.basename(p)[6:-4]}'" + (" (ZOOMED OUT)" if p.endswith("_wide.png") else "")
                  for p in images}
        inputs: dict = {"labels": labels}
        checklist = list(getattr(self, "checklist", None) or [])
        snapshot = None
        if hasattr(self.bridge, "scene_snapshot"):
            try:
                snapshot = self.bridge.scene_snapshot()
            except Exception:  # noqa: BLE001
                snapshot = None
        if checklist:
            from .checklist import checklist_text, match_items
            inputs["checklist"] = checklist_text(checklist)
            if snapshot is not None:
                shots = 0
                wanted = set(targets)
                from ..copilot import activity
                for entry in match_items(checklist, snapshot):
                    for number, copy in enumerate(entry["copies"], 1):
                        if activity.should_stop():
                            raise RuntimeError("Stopped by user.")
                        objects = [n for n in copy["objects"] if n in wanted]
                        if not objects or shots >= cfg.closeups:
                            continue
                        safe = re.sub(r"[^a-z0-9]+", "_", entry["item"].name.lower()).strip("_")[:24]
                        try:
                            paths = self.bridge.render_views(targets, ["three_quarter"], cfg.resolution, folder,
                                                             f"zoom_{safe}_{number}", focus=objects)
                        except TypeError:
                            paths = []                     # (an older bridge without close-ups)
                        for path in paths:
                            labels[path] = f"ZOOMED-IN close-up of {entry['item'].name} #{number}"
                        images += paths
                        shots += 1
        if snapshot is not None:
            try:
                from ..diagnostics.scene_audit import find_errors
                found = find_errors(snapshot, request, facts.console_text)
                inputs["measured"] = [f"[{f['severity']}] {f['what']} - fix: {f['fix']}" for f in found
                                      if f["severity"] in ("high", "medium") and f["kind"] != "MISSING?"][:15]
            except Exception:  # noqa: BLE001
                pass
            if checklist:
                from .checklist import match_items, presence_problems
                lines = presence_problems(match_items(checklist, snapshot))
                inputs.setdefault("measured", [])
                inputs["measured"] += [f"[check] {line} (if the images show it, it only has another name)"
                                       for line in lines][:8]
        return images, inputs

    def assess(self, request: str, facts: RunFacts, round_no: int = 0) -> CheckReport:
        cfg = self.cfg
        report = CheckReport(round=round_no, findings=analyze_console(facts.console_text), created=list(facts.created),
                             changed=list(facts.changed))
        try:
            from .scene_checks import geometry_problems
            report.geometry = geometry_problems(self.bridge, [n for n in facts.created + facts.changed
                                                              if facts.types.get(n, "MESH") in RENDERABLE])
        except Exception:  # noqa: BLE001 — a check must never break the result
            report.geometry = []
        report.folder = os.path.join(cfg.output_dir or os.path.join(os.path.expanduser("~"), "BlenderAIAgent", "checks"),
                                     time.strftime("%Y%m%d_%H%M%S") + f"_r{round_no}")
        if cfg.mode == "full":
            builder_cfg = self._fallback_vision(self._builder_loader())
            targets = [n for n in facts.created + facts.changed if facts.types.get(n, "") in RENDERABLE]
            reason = self._vision_skip_reason(request, facts, targets, builder_cfg.api_key) or \
                self._paused_reason(builder_cfg)
            if reason:
                report.vision_note = reason
            else:
                try:
                    folder = report.folder
                    from ..observability import run_trace
                    run_trace.note(f"CHECK  rendering {'every angle + zoom-in close-ups' if getattr(cfg, 'deep', False) else str(len(cfg.views)) + ' view(s)'} at {cfg.resolution}px into {folder}")
                    clock = time.time()
                    self._deep_inputs = None
                    if getattr(cfg, "deep", False):
                        report.images, self._deep_inputs = self._deep_renders(request, facts, targets, folder)
                    else:
                        report.images = self.bridge.render_views(targets, list(cfg.views), cfg.resolution, folder,
                                                                 "check")
                    run_trace.note(f"CHECK  {len(report.images)} image(s) rendered in {time.time() - clock:.1f}s; asking "
                                   f"the {getattr(builder_cfg, 'vision_provider', '') or 'gemini'} reviewer …")
                    llm = self._llm_for(builder_cfg)
                    clock = time.time()
                    critique = self._critique_with_retry(llm, request, report.images)
                    run_trace.note(f"CHECK  reviewer answered in {time.time() - clock:.1f}s: score {critique.score}, "
                                   f"missing {getattr(critique, 'missing', [])}")
                    if critique.raw_ok:
                        report.score, report.summary = critique.score, critique.summary
                        report.problems, report.keep = critique.problems, critique.keep
                        report.missing = list(getattr(critique, "missing", []) or [])
                    else:
                        report.vision_note = "the reviewer's answer could not be read"
                except sc.BuilderError as exc:
                    text = f"{exc} {exc.user_message}"
                    waiter = getattr(self, "quota_waiter", None)
                    critique = None
                    while waiter is not None and "llm" in locals() and ("429" in text or "quota" in text.lower()) and waiter(text):
                        try:                                     # quota back: look again (same AI)
                            critique = self._critique_with_retry(llm, request, report.images)
                            break
                        except sc.BuilderError as again:
                            text = f"{again} {again.user_message}"
                    if critique is not None and critique.raw_ok:
                        report.score, report.summary = critique.score, critique.summary
                        report.problems, report.keep = critique.problems, critique.keep
                        report.missing = list(getattr(critique, "missing", []) or [])
                    else:
                        report.vision_note = f"vision check skipped: {exc.user_message}"
                        self._maybe_pause(builder_cfg, text)
                except Exception as exc:  # noqa: BLE001 
                    report.vision_note = f"vision check skipped: {type(exc).__name__}: {exc}"
        serious = any(p.get("severity") in ("high", "medium") for p in report.problems) or bool(report.missing) \
            or (getattr(cfg, "strict_review", False) and bool(report.problems))
        report.needs_fix = (bool(report.actionable) or any(p.get("severity") == "high" for p in report.geometry)
                            or (report.score is not None and report.score < cfg.pass_score and serious))
        write_review(report, request)
        if report.folder and hasattr(self.bridge, "scene_snapshot"):
            try:   # the error finder: every problem it can measure, next to review.txt (read-only)
                from ..diagnostics.scene_audit import write_errors
                write_errors(self.bridge, request, facts.console_text, report.folder)
            except Exception:  # noqa: BLE001 — never let the error list break the check
                pass
        return report

    # After a quota error (429) the reviewer is not asked again - and nothing is rendered for it - until the quota
    # is back: a run once spent 77 s rendering check images that nobody could look at.
    PAUSE_DEFAULT_S = 600.0

    def _maybe_pause(self, builder_cfg, text: str) -> None:
        low = text.lower()
        if "429" not in low and "quota" not in low and "rate limit" not in low:
            return
        import re as _re
        found = _re.search(r"retry in ([\d.]+)\s*s", low)
        wait = min(3600.0, float(found.group(1)) + 5.0) if found else self.PAUSE_DEFAULT_S
        self._vision_paused()[getattr(builder_cfg, "vision_provider", "") or "gemini"] = time.time() + wait

    def _vision_paused(self) -> dict:
        """vision provider -> time when its quota should be back (lives as long as this verifier)."""
        if not hasattr(self, "_paused_until"):
            self._paused_until = {}
        return self._paused_until

    def _paused_reason(self, builder_cfg) -> str:
        provider = getattr(builder_cfg, "vision_provider", "") or "gemini"
        until = self._vision_paused().get(provider, 0.0)
        if until > time.time():
            return (f"vision check paused: the {provider.capitalize()} quota is used up until "
                    f"{time.strftime('%H:%M', time.localtime(until))} (no check renders until then)")
        return ""

    def _fallback_vision(self, builder_cfg):
        """The review always uses the AI picked in the panel - never another provider."""
        return builder_cfg

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
        if report.geometry:
            lines.append("Geometry problems (measured from real bounding boxes — fix these first):")
            lines += [f"- [{p['severity']}] {p['where']}: {p['issue']} -> {p['fix']}" for p in report.geometry[:10]]
        if report.missing:
            lines.append("MISSING from the scene - build each of these properly (real size, right place, right material):")
            lines += [f"- {item}" for item in report.missing[:12]]
        if report.score is not None and report.problems:
            lines.append(f"Visual review (score {report.score:g}/10): {report.summary}")
            lines += [f"- [{p['severity']}] {p['where']}: {p['issue']}" + (f" -> {p['fix']}" if p['fix'] else "") for p in report.problems[:10]]
            if report.keep:
                lines.append("Already right (keep): " + "; ".join(report.keep[:5]))
        if self._strict():
            lines.append("The goal is a flawless 10/10: fix EVERY item above, small ones too. Measure with object.measure "
                         "before and after: equal things must have equal heights and even spacing, doors and windows sit "
                         "flush in their wall with door bottoms on the floor.")
        lines.append("When done, reply with one short sentence about what you changed.")
        return "\n".join(lines)

    def announce(self, report: CheckReport, round_no: int) -> str:
        bits = []
        if report.actionable:
            bits.append(f"{len(report.actionable)} console problem(s)")
        high = [p for p in report.geometry if p.get("severity") == "high"]
        if high:
            bits.append(f"{len(high)} geometry problem(s)")
        if report.missing:
            bits.append(f"{len(report.missing)} missing element(s)")
        if report.score is not None and report.needs_fix:
            bits.append(f"vision score {report.score:g}/10")
        limit = "" if self.cfg.until_fixed else f"/{self.cfg.max_rounds}"
        return f"Auto-check found: {' + '.join(bits) or 'a problem'} - fixing it (round {round_no}{limit})."

    @staticmethod
    def badness(report: CheckReport) -> Tuple[int, int, int, float, int]:
        """Lower is better: console problems, high geometry problems, then (10 - vision score)."""
        high = sum(1 for p in report.geometry if p.get("severity") == "high")
        score = report.score if report.score is not None else 10.0
        return (len(report.actionable), high, len(report.missing), round(10.0 - score, 1), len(report.problems))

    @staticmethod
    def quota_gone(report: CheckReport) -> bool:
        note = (report.vision_note or "").lower()
        return "429" in note or "quota" in note

    def format_history(self, history: List[CheckReport]) -> str:
        if not history:
            return ""
        first, last = history[0], history[-1]

        def state(r: CheckReport) -> str:
            parts = []
            parts.append("console clean" if not r.actionable else f"{len(r.actionable)} console problem(s)")
            high = [p for p in r.geometry if p.get("severity") == "high"]
            if high:
                parts.append(f"{len(high)} geometry problem(s)")
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
            lines += [f"  - missing: {item}" for item in last.missing[:3]]
            lines += [f"  - [{p['severity']}] {p['where']}: {p['issue']}" for p in (last.geometry + last.problems)[:4]]
            lines.append("  (ask for more changes, or run it again)")
        notes = [r.vision_note for r in history if r.vision_note and r.score is None and "nothing new" not in r.vision_note
                 and "simple request" not in r.vision_note]
        if notes and not last.needs_fix:
            lines.append("  note: " + notes[-1])
        return "\n".join(lines)