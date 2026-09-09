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