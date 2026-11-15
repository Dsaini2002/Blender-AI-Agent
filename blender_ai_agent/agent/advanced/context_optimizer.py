"""ContextOptimizer"""

from typing import List, Optional


class ContextOptimizer:

    def __init__(self, context_manager):
        self._context_manager = context_manager

    def build_optimized_context(self, selected_object_names: Optional[List[str]] = None) -> dict:
        if selected_object_names:
            return self._context_manager.build_context(focus_object_names=selected_object_names)

        return self._context_manager.build_context()

    def estimate_context_size(self, context: dict) -> int:
        if "objects_summary" in context:
            return len(context["objects_summary"])
        if "focused_objects" in context:
            return len(context["focused_objects"])
        return 0