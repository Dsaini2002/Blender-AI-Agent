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