"""Debug output (timings etc.) only when BLENDER_AI_DEBUG=1 is set, so the console stays clean for users."""

import os


def debug(*args, **kwargs) -> None:
    if os.environ.get("BLENDER_AI_DEBUG", "").strip().lower() in ("1", "true", "yes", "on"):
        print(*args, **kwargs)
