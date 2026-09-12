# Security Policy

## Core principles

- **API keys are never stored, logged, or committed.** `ProviderConfig` only stores the *name* of an environment variable; the key itself is read at runtime via `os.environ`.
- **`.blend` files, logs, and benchmark artifacts must never contain secrets.**
- **Raw Python execution is a last resort**, not a primary interface. `PythonPowerTool` (`python.execute`) requires the `PYTHON_EXECUTION` permission level, blocks dangerous keywords (`import`, `exec`, `eval`, `__`, `open(`, `os.`, `sys.`, `subprocess`), and only exposes a restricted `bridge` object — never raw `bpy` or the filesystem.
- **Destructive operations require confirmation** by default (`PermissionConfig.destructive_write_requires_confirmation = True`).

## Permission levels

| Level | Meaning |
|---|---|
| `READ_ONLY` | Never modifies the scene |
| `SAFE_WRITE` | Reversible changes |
| `DESTRUCTIVE` | Irreversible changes (e.g. `object.delete`) — confirmation required |
| `PYTHON_EXECUTION` | Arbitrary restricted code — highest risk, disabled by default |

## Reporting a vulnerability

If you find a security issue (e.g. a way to bypass permission checks, exfiltrate an API key, or escape the `PythonPowerTool` sandbox), please open a private security advisory on GitHub rather than a public issue.