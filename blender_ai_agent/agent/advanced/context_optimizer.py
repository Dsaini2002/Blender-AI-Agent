"""
ContextOptimizer — Step 11.16
==================================
Hinglish: Phase 3 ka ContextManager already summary vs focused
context deta tha. Ye class ek layer aur upar hai — INSTRUCTION se
automatically decide karta hai konse objects "relevant" hain, taaki
caller ko manually object names batane ki zaroorat na pade jab
Blender-side "selection" available ho.

Large scene (2000 objects) mein, sirf selected/mentioned objects ka
context banta hai — poori scene nahi.
"""

from typing import List, Optional


class ContextOptimizer:

    def __init__(self, context_manager):
        # Dependency Injection — Phase 3 ka ContextManager reuse
        self._context_manager = context_manager

    def build_optimized_context(self, selected_object_names: Optional[List[str]] = None) -> dict:
        """
        Hinglish: Agar selection di gayi hai (Blender se), sirf unhi
        objects ka FULL detail — poori scene ka summary bhi nahi
        chahiye is case mein (Step 11.16 ka exact example: "Make the
        selected sword metallic" ko 2000 objects nahi chahiye).

        Agar koi selection nahi hai, fallback: compact summary
        (Phase 3 wala behavior).
        """
        if selected_object_names:
            return self._context_manager.build_context(focus_object_names=selected_object_names)

        return self._context_manager.build_context()

    def estimate_context_size(self, context: dict) -> int:
        """
        Hinglish: Simple proxy metric — context mein kitne "items"
        hain (objects_summary ya focused_objects ki length). Real
        token counting future mein isi jagah plug hoga.
        """
        if "objects_summary" in context:
            return len(context["objects_summary"])
        if "focused_objects" in context:
            return len(context["focused_objects"])
        return 0