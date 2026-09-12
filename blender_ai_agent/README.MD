# Blender AI Agent

Deterministic, typed tool system for controlling Blender programmatically — built as the foundation for a future LLM-driven Blender agent.

## Philosophy

> AI se start nahi karna. Pehle deterministic Blender foundation banana hai.
> Scene → Tools → Validation foundation strong hogi, tab Agent/LLM add karenge.

No LLM, no autonomous planning yet. Every tool is manually callable, fully typed, and independently testable — without ever opening Blender.

## Architecture
              ToolRegistry
                   │
    ┌──────────────┼───────────────┬───────────────┐
    ↓              ↓                ↓                ↓

ObjectTools MaterialTools ModifierTools CameraTools
│ │ │ │
└──────────────┴────────────────┴────────────────┘
↓
BlenderBridge
↓
bpy
↓
Blender


- **`BlenderBridge`** — the only place that touches raw `bpy`. Everything else depends on this abstraction, not on Blender directly.
- **`Tool` (ABC)** — every tool follows the same contract: `execute(input_dict) -> ToolResult`, using the Template Method pattern (`validate() -> run() -> error handling`).
- **`ToolRegistry`** — tools are looked up by name (e.g. `"object.create"`), so a future Agent never needs to know Python class names.
- **Typed input models** (`tools/models.py`) — every tool has a dataclass-based input contract with validation, instead of raw dicts.

## Status

### ✅ Phase 1 — Blender Foundation
Addon skeleton, `BlenderBridge`, `SceneInspector`, base `Tool`/`ToolRegistry`, first working tool, UI panel, unit tests.

### ✅ Phase 2 — Tool System (14 tools)

| Category | Tools |
|---|---|
| Scene | `scene.inspect` |
| Object | `object.create`, `object.delete`, `object.duplicate`, `object.rename`, `object.transform` |
| Material | `material.create`, `material.assign`, `material.modify` |
| Modifier | `modifier.add`, `modifier.remove`, `modifier.configure` |
| Camera/Render | `camera.create`, `camera.set`, `render.preview` |

Every tool has: a `Permission` level (`READ_ONLY` / `SAFE_WRITE` / `DESTRUCTIVE`), a typed input model, and unit + integration tests.

### ✅ Phase 3 — Agent Core

Natural language requests now translate into ordered, multi-step tool calls — without the LLM ever touching raw `bpy`.
                     USER
                       │
                       ▼
                ┌─────────────┐
                │ExecutionLoop│
                └──────┬──────┘
                       │
          ┌────────────┼────────────┐
          ▼            ▼             ▼
  ModelProvider   ToolCaller   ContextManager
          │            │
          ▼            ▼
  (OpenAI/Mock)   ToolRegistry
                       │
                       ▼
                     Tools
                       │
                       ▼
                BlenderBridge
                       │
                       ▼
                    Blender

| Component | File | Responsibility |
|---|---|---|
| `ModelProvider` (ABC) | `providers/base.py` | LLM-agnostic contract — real providers plug in without touching the Agent |
| `MockProvider` | `providers/mock_provider.py` | Scripted, deterministic responses for testing without any API key |
| `ModelRequest`/`ModelResponse` | `agent/models.py` | Typed LLM I/O — messages, tool definitions, tool calls, usage |
| `ContextManager` | `agent/context.py` | Compact scene summaries instead of dumping the entire scene to the LLM |
| `ToolCaller` | `agent/tool_caller.py` | Translates `ToolRegistry` ↔ LLM tool-call format; never crashes on unknown/hallucinated tools |
| `Agent` | `agent/agent.py` | Single-turn orchestration: one LLM call → optional tool execution |
| `Planner` | `agent/planner.py` | Breaks a model response into an ordered `Plan` of steps |
| `ExecutionLoop` | `agent/execution_loop.py` | Multi-turn loop: keeps calling the LLM until it returns a final answer, with a `max_iterations` safety limit |
| `ConversationState` | `agent/state.py` | Remembers message history so "make it red" can refer to a previously created object |

**Definition of Done demo (verified by test):**

> "Create a cube, move it to x=3, and rename it MainCube."

produces the plan `object.create → object.transform → object.rename`, executed sequentially, ending in a scene with an object named `MainCube` at `[3, 0, 0]`.

**Architecture rule enforced:** the LLM only ever sees tool *names* and *descriptions* — never `bpy`. An unknown or hallucinated tool name fails gracefully as a `ToolResult`, it never crashes the loop.

### ✅ Phase 4 — Reliability

Phase 3's Agent could execute tools — but had no way to know if an operation *actually* succeeded in the scene, no way to undo a partially-completed task, and no way to recover from a wrong object name without giving up.

> Tool response ≠ truth. The Blender scene is the source of truth.
                     USER
                       │
                       ▼
                ┌─────────────────────────┐
                │ RepairableExecutionLoop │
                └────────────┬────────────┘
                             │
                ┌────────────┼─────────────┐
                ▼            ▼              ▼
         TransactionManager  Validator   RecoveryManager
                │            │              │
                ▼            ▼              ▼
          SnapshotManager  (per-tool)   ToolCaller
                │                            │
                ▼                            ▼
          RollbackManager              ToolRegistry → Tools
                                              │
                                              ▼
                                       BlenderBridge
                                              │
                                              ▼
                                           Blender

| Component | File | Responsibility |
|---|---|---|
| `Validator` (ABC) + `ValidationResult` | `reliability/validator.py` | Contract: cross-check scene state against what a tool claimed to do |
| `ObjectExistsValidator`, `ObjectDeletedValidator`, `TransformValidator`, `MaterialAssignedValidator` | `reliability/tool_validators.py` | Concrete, per-operation validators that read the scene as source of truth |
| `SceneSnapshot` / `SnapshotManager` | `reliability/snapshot.py` | Captures a lightweight, point-in-time copy of relevant scene state |
| `TransactionManager` | `reliability/transaction.py` | `begin() → commit() / rollback()` lifecycle around a snapshot |
| `RollbackManager` | `reliability/rollback.py` | Restores the scene to a prior snapshot: deletes new objects, restores transforms, reports what couldn't be restored |
| `ErrorCode` / `ToolError` | `reliability/errors.py` | Classifies raw error strings into structured, typed errors with a `recoverable` flag |
| `RetryPolicy` | `reliability/retry.py` | Controlled retry limit — never retries blindly |
| `RecoveryManager` | `reliability/recovery.py` | For recoverable errors (e.g. a slightly wrong object name), inspects the scene and proposes a corrected tool call |
| `Logger` / `LogEvent` | `observability/logger.py` | Structured, queryable event log for every task, tool call, validation, and repair |
| `RepairableExecutionLoop` | `agent/repair_loop.py` | The Phase 4 loop: execute → validate → (if failed) diagnose → repair → retry → (if still failed) rollback |

**Self-repair example (verified by test):**

> "Move the red cube to x=5" — but the object is actually named `Red_Cube`.

object.transform(name="RedCube") → OBJECT_NOT_FOUND
↓
RecoveryManager inspects the scene, finds "Red_Cube"
↓
object.transform(name="Red_Cube") → SUCCESS
↓
TransformValidator confirms location actually changed
↓
Transaction commits


**Failure example (verified by test):**

An unrecoverable failure partway through a multi-step task (e.g. invalid input on the second tool call) rolls back *all* changes made during that transaction — the scene ends up exactly as it was before the task started.

| Feature | Phase 3 | Phase 4 |
|---|---|---|
| Validation | Trusts `ToolResult.success` | Cross-checks the actual scene |
| Rollback | ❌ | ✅ Snapshot-based |
| Transactions | ❌ | ✅ begin/commit/rollback |
| Error classification | Raw strings | ✅ Typed `ErrorCode` + `recoverable` flag |
| Recovery | ❌ | ✅ Auto-corrects recoverable errors (e.g. wrong object name) |
| Retry | ❌ | ✅ Controlled, policy-driven |
| Logging | ❌ | ✅ Structured event log per task |

### ✅ Phase 5 — Vision

The agent can now *see* the scene — not just query its structured state — and combine both to reason about visual correctness (framing, missing objects, low-confidence detections) before committing to a result.

> Blender scene data tells us what is there. Vision tells us what it looks like.

| Component | File | Responsibility |
|---|---|---|
| `VisionProvider` (ABC) + `MockVisionProvider` | `vision/providers/` | Same abstraction pattern as `ModelProvider` — real vision APIs plug in without touching the Agent |
| `VisualObservation` | `vision/models.py` | Structured vision output: description, detected objects, composition, lighting, issues, confidence |
| `Capture` / `RenderCapture` / `ViewportCapture` / `CameraCapture` | `vision/capture.py` | Blender-specific screenshot/render logic, kept out of the vision provider |
| `VisionAnalyzer` | `vision/analyzer.py` | Wires a `Capture` strategy to a `VisionProvider` |
| `VisionObserveTool` (`vision.observe`) | `vision/tool.py` | Exposes the vision pipeline as a standard tool — the Agent calls it exactly like `object.create` |
| `VisionContextManager` | `vision/context.py` | Combines structured scene context with a visual observation into one payload |
| `VisualValidator` | `vision/validator.py` | Checks an observation against expectations (required objects, minimum confidence, no issues) |
| `ObjectIdentifier` | `vision/identifier.py` | Grounds a visual description ("red cube") to an actual scene object name ("Red_Cube") |
| `VisionError` / `classify_vision_exception` | `vision/errors.py` | Structured vision-specific error codes, following the same pattern as `reliability/errors.py` |
| `HumanInTheLoopGate` | `vision/human_in_loop.py` | Vision-driven suggestions never auto-execute destructive tools — they require explicit confirmation |

**Confidence is never treated as ground truth:** `VisionObserveTool` flags `low_confidence_warning` on uncertain observations instead of silently trusting them, and `check_confidence()` can hard-stop a workflow before it acts on an unreliable observation.

**Vision integrates with Phase 4's reliability loop** via `RepairableExecutionLoop.validate_visually()` — an explicit, opt-in step (image analysis is expensive, so it's never run automatically after every tool call).


### ✅ Phase 6 — Copilot UX

The engine built across Phases 1–5 is now exposed through a Blender-native chat interface, without the UI layer ever containing business logic or touching `bpy` directly.

> UI → CopilotController → Agent → Tool System → Blender
                USER
                  │
                  ▼
        ┌──────────────────┐
        │  AIAgentPanel    │  (Blender sidebar)
        └────────┬─────────┘
                  │
                  ▼
        ┌──────────────────┐
        │ CopilotController│
        └────────┬─────────┘
                  │
    ┌─────────────┼─────────────────┐
    ▼             ▼                 ▼

CopilotSession ProgressState ConfirmationManager
│ │ │
▼ ▼ ▼
SuggestionEngine TaskHistory EventBus
│
▼
RepairableExecutionLoop (Phase 3 + 4)
│
▼
ToolRegistry → Tools (15) + vision.observe
│
▼
BlenderBridge → Blender


| Component | File | Responsibility |
|---|---|---|
| `CopilotController` | `copilot/controller.py` | The single entry point between UI and Agent. Accepts any object with a `.run(text)` method via dependency injection — works with `Agent`, `ExecutionLoop`, or `RepairableExecutionLoop` interchangeably |
| `CopilotSession` / `CopilotMessage` | `copilot/session.py`, `copilot/messages.py` | Structured, displayable chat history — kept separate from the LLM's internal `ConversationState` (Phase 3) |
| `ProgressState` | `copilot/progress.py` | Live per-step task progress: `○ pending → → running → ✓ done / ✗ failed` |
| `ConfirmationManager` | `copilot/confirmations.py` | Destructive-permission actions require explicit approval before executing |
| `SuggestionEngine` | `copilot/suggestions.py` | Scene-aware "what to do next" suggestions, derived live from `scene.inspect` — never a hardcoded list |
| `CopilotContextBuilder` | `copilot/context.py` | Selection / active object / active camera, always derived fresh from Blender state — never an independent source of truth |
| `TaskHistory` | `copilot/history.py` | In-memory recent-task log (session-scoped — permanent memory is Phase 7, intentionally not built here) |
| `EventBus` / `CopilotEvent` | `copilot/events.py` | Publish/subscribe so the UI never reaches into the Agent's internals |
| `compute_diff` / `SceneDiff` | `copilot/diff.py` | Before/after scene comparison, built directly on Phase 4's `SceneSnapshot` |
| `AIAgentPanel`, `copilot_submit` operator | `ui/panel.py` | The actual Blender sidebar UI — a thin shell that only forwards typed text to `CopilotController.submit()` |

**Architecture rule enforced:** nothing under `copilot/` imports `bpy`, and `ui/panel.py` contains no tool logic — every action flows through `CopilotController`.

**Definition of Done:**

| Item | Status |
|---|---|
| Blender sidebar panel + chat input/output | ✅ |
| Conversation session | ✅ |
| Agent integration | ✅ |
| Task progress | ✅ |
| Tool execution visibility | ✅ |
| Confirmation system + permission visibility | ✅ |
| Cancel/stop | ✅ |
| Error presentation | ✅ |
| Context-aware suggestions | ✅ |
| Selection awareness | ✅ |
| Scene diff | ✅ |
| Task history | ✅ |
| Event-driven UI | ✅ |
| Tests, docs, git history, GitHub push | ✅ |

**Known limitation:** the panel currently wires to a `MockProvider` with no scripted responses (`get_copilot_controller()` in the root `__init__.py`) — a real LLM provider (OpenAI/Anthropic) needs to be plugged in before the chat is usable inside real Blender with real natural-language input. Swapping it in is a one-line change, by design (Open/Closed Principle — `ModelProvider` abstraction from Phase 3).

### ✅ Phase 7 — Memory & Skills

The agent can now remember useful context across tasks and execute high-level, parameterized, multi-tool workflows — without ever treating memory as a replacement for the scene's source of truth.

> Memory ka matlab har conversation save karna nahi hai — useful information store karni hai.
                     USER
                       ↓
                    AGENT
                       ↓
          ┌────────────┴────────────┐
          ↓                         ↓
     Memory System             Skill System
          ↓                         ↓
  MemoryContextBuilder        SkillRegistry
          ↓                         ↓
          └────────────┬────────────┘
                       ↓
          MemorySkillOrchestrator
                       ↓
                Tools (via ToolCaller)
                       ↓
                   Blender

| Component | File | Responsibility |
|---|---|---|
| `Memory`, `UserPreference`, `ProjectMemory`, `TaskMemory` | `memory/models.py` | Typed memory records — polymorphic subclasses per category |
| `MemoryStore` (ABC) + `InMemoryStore` | `memory/store.py` | Storage abstraction — the Agent is never coupled to a specific backend (JSON/SQLite/vector DB can plug in later) |
| `MemoryManager` | `memory/manager.py` | The single interface the Agent uses: `remember()` / `recall()` / `forget()` |
| `MemoryRetriever` | `memory/retriever.py` | Scores every memory against a query and returns only what's relevant, not everything stored |
| `MemoryPolicy` | `memory/policies.py` | Decides what should be stored, retrieved, or expired — secrets (API keys, passwords, tokens) are never stored |
| `MemoryContextBuilder` | `memory/context.py` | Turns relevant memories into a compact, categorized summary instead of raw dumps |
| `Skill` (ABC) + `SkillResult` | `skills/base.py` | A reusable, multi-tool workflow — high-level, parameterized, and never touches `bpy` directly |
| `SkillRegistry` | `skills/registry.py` | Name-based lookup plus `find_best_match()` for skill selection, mirroring `ToolRegistry` |
| `ProductShowcaseSkill` | `skills/builtins/product_showcase.py` | A working example skill: create → material → assign → camera, entirely through existing tools |
| `SkillValidator` | `skills/validation.py` | Reuses Phase 4's `Validator`s to confirm a skill's steps actually happened in the scene, not just that the skill reported success |
| `MemorySkillOrchestrator` | `memory/orchestrator.py` | The key integration point: retrieves relevant memory, selects a matching skill, and merges the two into a personalized execution |

**Skill permissions:** every skill exposes `required_permissions()`, so a skill involving `object.delete` (or any `DESTRUCTIVE` tool) can be flagged for confirmation before it runs — skills never get unrestricted access by default.

**Scene remains the source of truth:** memory can help resolve references ("move it") and personalize workflows, but it never substitutes for `scene.inspect` — exactly the same principle carried forward from Phase 1.


### ✅ Phase 8 — Benchmark

The agent no longer just "does things" — its performance can now be objectively measured. The core principle carries forward from Phase 4: an agent's own "Done ✓" is never trusted as truth. The Blender scene, read fresh through `BlenderBridge`, is the only source of truth an evaluation trusts.

> Agent Response ≠ truth. Blender Scene → Evaluator → Actual Result.

BenchmarkTask
↓
BenchmarkRunner (fresh, isolated environment per task)
↓
Agent executes the instruction
↓
ValidationRules read the actual scene
↓
Evaluator → score (PASS / FAIL / partial)
↓
MetricCalculator → aggregate stats across a suite
↓
FailureAnalyzer / BenchmarkComparator / BenchmarkReporter


| Component | File | Responsibility |
|---|---|---|
| `BenchmarkTask`, `ValidationResult`, `BenchmarkResult` | `benchmarks/models.py` | Typed task definitions and results — instruction, expected state, rules, timeout, score, status |
| `ValidationRule` (ABC) + concrete rules | `benchmarks/validation_rules.py` | `ObjectExistsRule`, `ObjectTypeRule`, `TransformRule`, `MaterialRule`, `ModifierRule` — each reads the scene directly through the bridge, never trusting the tool's own success flag |
| `Evaluator` | `benchmarks/evaluator.py` | Runs a task's rules against the actual scene; supports both equal-weight and weighted scoring |
| `BenchmarkRunner` | `benchmarks/runner.py` | Executes a task's full lifecycle with a fresh, isolated agent+bridge per task — one task's changes never leak into the next |
| `MetricCalculator` | `benchmarks/metrics.py` | Aggregates a suite's results into success rate, average score, duration, tool calls, retries, and rollbacks |
| `DatasetLoader` | `benchmarks/dataset_loader.py` | Builds `BenchmarkTask` objects from task definitions (dict/JSON-shaped) |
| `FailureAnalyzer` | `benchmarks/failure_analysis.py` | Classifies failures into categories (`VALIDATION_FAILURE`, `TOOL_FAILURE`, `RECOVERY_FAILURE`, `TIMEOUT`, etc.) instead of a generic "failed" |
| `BenchmarkComparator` | `benchmarks/comparator.py` | Detects regressions and improvements between two benchmark runs, overall and per-category |
| `BenchmarkReporter` | `benchmarks/reporter.py` | Produces the human-readable summary report |
| `benchmarks/tasks/basic_tasks.py` | — | A working example task ("Create a cube named Hero.") wired end-to-end through the runner |

**Isolation guarantee (verified by test):** running the same task twice in a suite produces two independent PASS results — no state leaks between tasks, because each task gets its own fresh `FakeBridge`/`BlenderBridge` and agent instance.

**Scoring is partial, not binary:** a task with 2 of 2 rules passing scores 100%, but a task with 1 of 2 scores 50% — this surfaces *how close* a failing task got, not just that it failed.


### ✅ Phase 9 — Advanced Agents & Blender Capabilities

The agent moved from handling single, controlled operations to decomposing complex, high-level instructions into dependency-ordered sub-tasks, executing them with checkpoint-based recovery, and gaining new Blender capabilities (Geometry Nodes, animation, a tightly restricted Python escape hatch).

> Blender = Execution Environment. Agent = Intelligence. Tools = Actions. Vision = Observation. Validator = Truth Check.
          Complex Instruction
                   ↓
           TaskDecomposer
                   ↓
              TaskGraph (dependency order)
                   ↓
        AdvancedOrchestrator
                   ↓
    ┌──────────────┼──────────────┐
    ↓              ↓              ↓

Checkpoint Skill/Tool AgentStateMachine
(per subtask) execution (IDLE→PLANNING→
↓ ↓ EXECUTING→...)
└──────────────┴──────────────┘
↓
Failure? → rollback to LATEST checkpoint
(not a full restart)


| Component | File | Responsibility |
|---|---|---|
| `TaskDecomposer` | `agent/advanced/decomposer.py` | Breaks a high-level instruction into `SubTask`s with declared dependencies |
| `TaskGraph` | `agent/advanced/task_graph.py` | Topologically sorts sub-tasks so dependencies always execute before dependents; detects cycles |
| `CheckpointManager` | `agent/advanced/checkpoints.py` | Named checkpoints built on Phase 4's `SnapshotManager`/`RollbackManager` — failure rolls back to the *latest* checkpoint, not the start |
| `AgentStateMachine` | `agent/advanced/state.py` | Enforces valid lifecycle transitions (e.g. `IDLE` can't jump straight to `COMPLETED`) |
| `AdvancedOrchestrator` | `agent/advanced/orchestrator.py` | Ties decomposition + graph ordering + checkpointing + state machine together into one complex-task runner |
| `SkillPermissionChecker` | `skills/advanced_permissions.py` | Determines a skill's overall risk level and whether it needs confirmation, based on the tools it composes |
| `CreateGeometryNodesTool` (`geometry_nodes.create`) | `tools/geometry_node_tools.py` | Adds a Geometry Nodes modifier + node group to an object |
| `InsertKeyframeTool` (`animation.keyframe`) | `tools/animation_tools.py` | Inserts a location keyframe at a given frame |
| `PythonPowerTool` (`python.execute`) | `tools/python_power_tool.py` | A deliberately restricted escape hatch — blocked keywords (`import`, `exec`, `__`, etc.), a minimal builtins allowlist, and a new `PYTHON_EXECUTION` permission level. Used only when no structured tool exists |
| `Tracer` | `observability/tracer.py` | Nested trace spans (`Task → Modeling → Tool 1/2/3`) instead of Phase 4's flat event log |
| `VisualSimilarityComparator` | `vision/similarity.py` | Compares two `VisualObservation`s by object overlap — a transparent, explainable score, not an unexplained ML number |

**Recovery without full restart (verified by test):** when a sub-task fails partway through a multi-part task, the orchestrator rolls back only to the most recent checkpoint — earlier completed sub-tasks are not redone.

**Python execution stays a last resort:** it carries the highest permission level (`PYTHON_EXECUTION`), runs against a restricted builtins set, and only has access to the `bridge` object — never raw `bpy` or the filesystem.


### ✅ Phase 10 — Production & Community

The project moved from "a working system" to "a system others can install, configure, and extend."

| Component | File | Responsibility |
|---|---|---|
| `AgentConfig`, `ProviderConfig`, `PermissionConfig` | `config/settings.py` | Typed, structured configuration — API keys are read from an environment variable **name** at runtime, never stored or logged |
| `ProviderRegistry` | `providers/registry.py` | Register/create model providers by name — adding a new provider never requires touching the `Agent` |
| Tool SDK | `sdk/tools.py` | `create_tool()` builds a fully-formed `Tool` subclass + input dataclass from a few arguments, reducing boilerplate for third-party contributors |
| `CONTRIBUTING.md`, `SECURITY.md` | repo root | Contribution workflow and the project's security principles |
| Issue/PR templates | `.github/` | Structured bug reports, feature requests, benchmark issues, and PR checklists |
| `docs/tools.md` | — | Step-by-step guide for authoring a new `Tool` |

**Security guarantee carried through every phase:** no API key, secret, or credential is ever stored in code, config objects, logs, or `.blend` files — only environment variable *names* are configured; values are read at runtime.

---

## 🏁 Project Status: Phases 1–10 Complete