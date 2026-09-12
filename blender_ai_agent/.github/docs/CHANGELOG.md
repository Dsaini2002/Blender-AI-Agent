# Changelog

All notable changes to this project are documented here, organized by development phase.

## [0.10.0] — Phase 10: Production & Community
- Added `AgentConfig`, `ProviderConfig`, `PermissionConfig` — typed configuration, API keys read from environment variables only, never stored
- Added `ProviderRegistry` for pluggable model providers
- Added Tool SDK (`sdk/tools.py`) to reduce boilerplate when authoring new tools
- Added `CONTRIBUTING.md`, `SECURITY.md`, issue templates, PR template
- Added `docs/tools.md` developer guide

## [0.9.0] — Phase 9: Advanced Agents
- Added `TaskDecomposer`, `TaskGraph` (dependency-ordered execution), `CheckpointManager`
- Added `AgentStateMachine` with enforced valid transitions
- Added `AdvancedOrchestrator` — checkpoint-based recovery without full task restart
- Added Geometry Nodes tool, Animation (keyframe) tool
- Added `PythonPowerTool` — restricted, permission-gated raw Python escape hatch
- Added `Tracer` for nested execution traces
- Added `VisualSimilarityComparator`

## [0.8.0] — Phase 8: Benchmark
- Added `BenchmarkTask`, `ValidationRule` hierarchy, `Evaluator` (partial + weighted scoring)
- Added `BenchmarkRunner` with per-task isolation
- Added `MetricCalculator`, `FailureAnalyzer`, `BenchmarkComparator`, `BenchmarkReporter`
- Added `DatasetLoader` and first working benchmark task

## [0.7.0] — Phase 7: Memory & Skills
- Added typed `Memory` model with `UserPreference`/`ProjectMemory`/`TaskMemory` subclasses
- Added `MemoryStore` abstraction, `MemoryManager`, `MemoryRetriever`, `MemoryPolicy`, `MemoryContextBuilder`
- Added `Skill` abstraction, `SkillRegistry`, `ProductShowcaseSkill`
- Added `MemorySkillOrchestrator` — memory-personalized skill execution

## [0.6.0] — Phase 6: Copilot UX
- Added `CopilotController`, `CopilotSession`, `CopilotMessage`
- Added `ProgressState`, `ConfirmationManager`, `SuggestionEngine`
- Added `CopilotContextBuilder`, `TaskHistory`, `EventBus`, `SceneDiff`
- Wired the Blender sidebar panel to the Copilot layer

## [0.5.0] — Phase 5: Vision
- Added `VisionProvider` abstraction and `MockVisionProvider`
- Added `Capture` classes (viewport/render/camera), `VisionAnalyzer`
- Added `vision.observe` tool, `VisionContextManager`, `VisualValidator`
- Added `ObjectIdentifier`, vision error classification, confidence gating
- Added `HumanInTheLoopGate` for destructive vision-suggested actions

## [0.4.0] — Phase 4: Reliability
- Added `Validator` abstraction and concrete scene validators
- Added `SceneSnapshot`/`SnapshotManager`, `RollbackManager`, `TransactionManager`
- Added structured `ToolError` classification, `RetryPolicy`, `RecoveryManager`
- Added `RepairableExecutionLoop` — the full execute → validate → repair → retry → rollback cycle
- Added structured `Logger`

## [0.3.0] — Phase 3: Agent Core
- Added `ModelProvider` abstraction and `MockProvider`
- Added typed `ModelRequest`/`ModelResponse` models
- Added `ContextManager`, `ToolCaller`, `Agent`
- Added `Planner`, `ExecutionLoop` (multi-step, multi-turn), `ConversationState`

## [0.2.0] — Phase 2: Tool System
- Added `Tool` (ABC), `ToolResult`, `Permission` enum, Template Method `execute()`
- Added `ToolRegistry`
- Added 15 tools across scene, object, material, modifier, and camera/render categories

## [0.1.0] — Phase 1: Blender Foundation
- Added `BlenderBridge` (sole `bpy` interface)
- Added `SceneInspector`, base `Tool`, basic UI panel
- First deterministic tool: `scene.inspect`