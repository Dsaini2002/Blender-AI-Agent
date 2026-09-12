# Contributing to Blender AI Agent

Thanks for your interest in contributing! This project follows a structured, test-driven workflow.

## Development workflow

1. **Discuss first** — open an issue describing the tool/skill/fix before writing code, especially for anything touching `reliability/`, `agent/`, or permissions.
2. **Write tests first (or alongside)** — every new `Tool`, `Skill`, or `Provider` needs unit tests using the existing `FakeBridge`/`MockProvider`/`MockVisionProvider` pattern in `tests/fakes.py`. No PR is merged without tests.
3. **Run the full suite** before pushing:
```bash
   python run_tests.py
```
4. **Small, focused commits** — one logical change per commit, with a `feat:` / `fix:` / `docs:` / `test:` / `chore:` prefix.
5. **Update the README** if your change adds a new phase-level capability.

## Adding a new Tool

See `docs/tools.md` for the full guide. Short version:

1. Define a typed input dataclass in the relevant `tools/*_tools.py` file (or use `sdk/tools.py`'s `create_tool()` helper for less boilerplate).
2. Extend `Tool`, set `name`, `description`, `permission`, `input_model`.
3. Implement `run()` — never `execute()` directly (the base class handles validation via the Template Method pattern).
4. Register it in `_register_tools()` in the root `__init__.py`.
5. Add a `FakeBridge`-based test in `tests/`.

## Adding a new Skill

See `docs/skills.md`. Skills compose existing tools through `ToolCaller` — they must never call `bpy` directly.

## Adding a new Provider

Implement `ModelProvider` (`providers/base.py`), register it with `ProviderRegistry` (`providers/registry.py`). Never hardcode API keys — read them via `ProviderConfig.get_api_key()`, which reads from an environment variable name, never a stored value.

## Code style

- Comments and docstrings in this codebase are written in Hinglish, explaining both *what* and *why* (especially OOP/design decisions). Please follow this style for consistency.
- Keep `BlenderBridge` as the only place that imports `bpy`.
- Prefer dependency injection over creating dependencies inside a class.

## Reporting bugs / requesting features

Use the issue templates in `.github/ISSUE_TEMPLATE/`.