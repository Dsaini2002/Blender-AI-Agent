"""LiveMemory: what the Copilot remembers between requests and between Blender sessions.

Three kinds of memory:
  user_preference  things the user says about how they like work done ("I prefer low poly", "always use metres",
                   "never delete my objects"; Hindi phrasing works too)
  project_memory   what was built in this .blend file (so "make the table red" works the next day)
  task_memory      past requests and what they produced (helps with "make another one like before")

Before every request the relevant memories are turned into a short block of text for the model. The Blender scene
stays the source of truth: memory only helps resolve references and style, it never replaces scene.inspect.
"""

import os
import re
from typing import Iterable, List, Optional

from .models import Memory, ProjectMemory, TaskMemory, UserPreference
from .policies import MemoryPolicy
from .retriever import MemoryRetriever
from .store import InMemoryStore, JsonFileStore

# Only clear statements about the user's own taste / standing rules ("I prefer...", "from now on...", "remember
# that...", "my style is..."), never ordinary scene instructions like "always keep the water blue".
_PREFERENCE = re.compile(
    r"(?:^|[.!?;\n]\s*)("
    r"(?:i|we)\s+(?:always\s+|usually\s+|generally\s+)?(?:prefer|like|love|hate|dislike|don't like|do not like)\b[^.!?;\n]*"
    r"|(?:please\s+)?(?:from now on|by default|in future|for all future|remember(?: that)?)\b[^.!?;\n]*"
    r"|my\s+(?:style|preference|favou?rite)[^.!?;\n]*"
    r"|(?:mujhe|hume|humein)\b[^.!?;\n]*\b(?:pasand|psand)\b[^.!?;\n]*"
    r"|(?:aage se|ab se)\b[^.!?;\n]*"
    r")", re.IGNORECASE)
MAX_PREFERENCE_REQUEST_CHARS = 300

MAX_PREFERENCES_IN_PROMPT = 8
MAX_TASKS_IN_PROMPT = 3
MAX_PROJECT_IN_PROMPT = 5


def default_memory_path() -> str:
    env = os.environ.get("BLENDER_AI_MEMORY_FILE", "").strip()
    return os.path.expanduser(env) if env else os.path.join(os.path.expanduser("~"), "BlenderAIAgent", "memory_v2.json")


class LiveMemory:

    def __init__(self, store=None, policy: Optional[MemoryPolicy] = None):
        self._store = store if store is not None else InMemoryStore()
        self._policy = policy or MemoryPolicy(expiry_days=180)
        self._retriever = MemoryRetriever(self._store, threshold=0.6)

    @classmethod
    def from_file(cls, path: Optional[str] = None) -> "LiveMemory":
        return cls(JsonFileStore(path or default_memory_path()))

    # ------------------------------------------------------------------ writing
    def learn_from_request(self, text: str) -> List[str]:
        """Save preference statements found in the request. Returns what was saved."""
        saved = []
        if len(text or "") > MAX_PREFERENCE_REQUEST_CHARS:
            return saved
        existing = {m.content.lower() for m in self._all("user_preference")}
        for match in _PREFERENCE.finditer(text or ""):
            sentence = re.sub(r"\s+", " ", match.group(1)).strip(" ,.")
            if len(sentence.split()) < 3 or sentence.lower() in existing:
                continue
            if not self._policy.should_store(sentence):
                continue
            self._store.save(UserPreference(content=sentence[:240]))
            existing.add(sentence.lower())
            saved.append(sentence)
        return saved

    def record_task(self, request: str, reply: str, objects: Iterable[str], project_id: str) -> None:
        objects = [o for o in dict.fromkeys(objects) if o][:40]
        request = re.sub(r"\s+", " ", request or "").strip()
        if not request or not self._policy.should_store(request):
            return
        built = f" -> objects: {', '.join(objects)}" if objects else ""
        self._store.save(TaskMemory(content=f"{request[:200]}{built}"[:600], metadata={"project": project_id}))
        if objects and project_id and project_id != "unsaved":
            self._store.save(ProjectMemory(content=f"Built for '{request[:120]}': {', '.join(objects)}"[:600],
                                           project_id=project_id))

    def forget_all(self) -> None:
        clear = getattr(self._store, "clear", None)
        if clear is not None:
            clear()
            return
        for memory in list(self._all()):
            self._store.delete(memory.id)

    # ------------------------------------------------------------------ reading
    def context_for(self, request: str, project_id: str = "") -> str:
        """Short text block for the model; '' when nothing useful is stored."""
        preferences = [m.content for m in self._recent(self._all("user_preference"), MAX_PREFERENCES_IN_PROMPT)]
        project = [] if project_id in ("", "unsaved") else [m.content for m in self._recent(
            [m for m in self._all("project_memory") if getattr(m, "project_id", "") == project_id], MAX_PROJECT_IN_PROMPT)]
        tasks = [m.content for m in self._retriever.retrieve(request, limit=10)
                 if m.type == "task_memory" and self._policy.should_retrieve(m)][:MAX_TASKS_IN_PROMPT]
        if not (preferences or project or tasks):
            return ""
        lines = ["MEMORY (from earlier sessions; the live scene list above is the truth if they disagree):"]
        if preferences:
            lines.append("User preferences — follow them unless this request says otherwise:")
            lines += [f"- {p}" for p in preferences]
        if project:
            lines.append("Built earlier in this file:")
            lines += [f"- {p}" for p in project]
        if tasks:
            lines.append("Similar earlier requests:")
            lines += [f"- {t}" for t in tasks]
        return "\n".join(lines)

    def preferences(self) -> List[str]:
        return [m.content for m in self._recent(self._all("user_preference"), 50)]

    def count(self) -> int:
        return len(self._all())

    # ------------------------------------------------------------------ helpers
    def _all(self, memory_type: Optional[str] = None) -> List[Memory]:
        memories = self._store.all() if hasattr(self._store, "all") else self._store.search("")
        memories = [m for m in memories if self._policy.should_retrieve(m)]
        return [m for m in memories if memory_type is None or m.type == memory_type]

    @staticmethod
    def _recent(memories: List[Memory], limit: int) -> List[Memory]:
        return sorted(memories, key=lambda m: m.created_at, reverse=True)[:limit]
