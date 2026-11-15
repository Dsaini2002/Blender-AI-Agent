# Changelog

All notable changes to this project are documented here, organized by development phase.

## [0.15.3] — See what the check did
- Every check round writes `review.txt` next to its images (score, missing, each problem with its fix, geometry and console findings, the decision) and `fix_prompt.txt` (what the agent was told); the run log and `_report.txt` get an AUTOMATIC CHECK ROUNDS section; panel button **Check Images**
- When the AI that takes over after a quota error also fails (an expired Groq key), the next one is tried; a bad key gets a clear "paste a new key" message
- Argument names like `light_location` / `camera_rotation` are understood (lights no longer all land at [0, 0, 3])
- Books, cushions, vases ... may differ in height: no more "uneven repeats" rounds for them
- 1,544 tests

## [0.15.2] — Things inside each other
- The automatic geometry check finds furniture standing inside other furniture (a desk inside a bookshelf, a wardrobe through a shelf) and furniture pushed into a wall, with the exact move that clears it (towards the room for walls); chairs under tables, lamps on nightstands, rugs and hanging lights are allowed
- New `object.move_by`: moves every part of a library model by an offset, so a model never comes apart
- The vision reviewer is told to name both objects when two things are inside each other
- 1,536 tests; the real-Blender check finds and clears a desk inside a bookshelf

## [0.15.1] — No more hangs
- A rate-limit (429) wait is never longer than 20 s and Stop ends it at once; a used-up daily quota is reported at once instead of sleeping (one villa run slept 15+ minutes); the Gemini SDK call has a 120 s timeout
- When the AI's quota is used up mid-run, the Copilot continues with another AI that has a key (Gemini -> Groq / Claude)
- Only one run at a time: a run left going in the background (after File > New or a model switch) is stopped and blocks a new Generate until it ends; the panel shows "Stop previous run"
- A long, detailed request always goes to the team: the simple house skill no longer takes a villa spec
- Tool names like 'call:mesh.boundary_wall' or 'functions.object.create' are understood
- 1,530 tests

## [0.15.0] — Edit anything, luxury interiors, key box
- API key box in the panel: choose a provider without a key -> key box + Get key + Submit Key (hidden once saved); provider picker always visible
- Editing: `object.recolor` (colour words in English and Hindi, textures kept, only the named objects change); `mesh.building` called again with the same name rebuilds that building in place with only the changes (remembered in the .blend); short change requests skip team planning
- `mesh.building`: roof = flat / terrace (roof garden) / gable / hip, roof_pitch; wall / accent / roof / frame / glass colours; per-building materials
- 14 interior models: double (king) bed, nightstand, table lamp, pendant light, chandelier, floor lamp, rug, wall art, potted plant, armchair, coffee table, TV unit, curtains, mirror (51 models)
- Fixed: an indoor 'ceiling_lamp' no longer becomes a 3.9 m street lamp; requests naming a library model no longer go to script building
- Vision: after a quota error (429) no check images are rendered until the quota is back; with a Claude key the check moves to Claude
- 1,520 tests; the real-Blender check also edits a roof, recolours and places the interior models

## [0.14.0] — Buildings, campus tools, Claude
- `mesh.building`: complete multi-storey buildings (rect / L / U / courtyard, G+N) with windows, balconies, corridors, entrance + name board, stairs, lifts, furnished rooms and ground-floor halls in one call
- Campus tools: `mesh.boundary_wall` (gate, cabin, boom barrier, name arch), `text.create`, `scene.organize`, `scene.save`; 12 new library models (bicycle, bicycle parking, bed, study table, chair, wardrobe, ceiling fan, table-tennis table, dining table, sofa, bookshelf, reception desk); brick material
- `mesh.field_markings` places the nets / hoops / goals / wickets itself; a duplicate on the same court is refused
- Anthropic Claude provider (Sonnet / Opus / Haiku 5.5) over REST, key in the panel; Claude can also do the picture check
- Team mode no longer silently falls back to one agent: role synonyms, code fences and a fallback plan from the request's sections; every skip is logged
- Fix rounds: text-only answers are sent back to work; far-off results are re-planned into team steps
- Check renders: a cutaway view of every building, framing without the big lawn; the geometry check ignores generated multi-part objects
- `material.recipe` names a material itself when the name is missing
- Revert restores names without `.001` copies (checked in real Blender)
- `scripts/real_blender_check.py` + a GitHub job that runs the add-on in real Blender 5.2.1: builds a campus, runs a whole Generate click (team plan -> 4 role steps -> check renders -> vision) with scripted AI answers
- Run diagnostics: `live_trace.txt` (written while running, thread stacks after 90 s without progress), `<time>_report.txt` (errors, timings, plan, timeline), `crash_trace.txt`; panel buttons View Report / Open Live Trace
- Fixed: team steps no longer go to a skill shortcut (a "sun and camera" step went to build.iterate); a missing `import os` when starting the Copilot
- 1,503 tests

## [0.13.0] — New panel, first-run setup, faster checks
- New Copilot panel: status + model picker, API key field in the panel (saved in add-on preferences), Scene Context, tall AI Prompt box with full multi-line Ctrl+V, Generate with AI, live steps and auto-check round, Recent Tasks (View Logs / Retry), Revert AI Changes (checkpoint before each run), Modeling / Material / Lighting quick actions
- Gemini works without the Google SDK (REST fallback), so a fresh Blender needs no pip installs
- Previews and auto-check renders use fast EEVEE (960x540); Cycles only when asked, so Blender no longer freezes
- Check renders hide roofs and the walls nearest each camera so the vision review sees inside halls and stadiums
- `mesh.field_markings` builds the coloured court surface and white lines for each sport
- Library: badminton racket, shuttlecock, nets for each sport, basketball hoop, football goal, cricket wicket, stadium light, park bench, palm tree (25 models)
- Light / camera / object tools fill in a missing name; seating is built with `mesh.grandstand` outside the court
- GitHub workflows: tests on every push, and a release zip (`blender_ai_agent.zip`) built for each `v*` tag
- 1,462 tests

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