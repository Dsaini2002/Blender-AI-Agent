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

### phase 5 start
lets now start phase 
do now