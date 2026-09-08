markdown
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

### ⏳ Phase 3+ — Not started
Agent Core (LLM + tool calling), Reliability, Vision, Copilot UX, Memory, Benchmarking, Advanced Agents, Community/Product.

## Running tests

Tests run without opening Blender, using a fake `bpy` stub:

```bash
python run_tests.py
```

## Installing in Blender

1. Zip or select the `blender_ai_agent/` folder.
2. Blender → Preferences → Add-ons → Install → select the folder/zip.
3. Enable the addon.
4. Open the sidebar (`N` key) → "AI Agent" tab.

## OOP principles applied

- **Encapsulation** — all raw `bpy` calls live only in `BlenderBridge`.
- **Dependency Injection** — every tool/inspector receives its dependencies via constructor, not by creating them internally.
- **Abstraction** — `Tool(ABC)` defines a contract subclasses must fulfill.
- **Polymorphism** — 14 different tools, one uniform `execute()` interface.
- **Template Method Pattern** — `execute()`'s flow (validate → run → catch errors) is fixed in the base class; subclasses only implement `run()`.
- **Single Responsibility Principle** — one tool = one job; `BlenderBridge`, `ToolRegistry`, and `SceneInspector` each have exactly one concern.