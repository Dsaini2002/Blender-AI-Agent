"""
VisionContextManager — Step 5.4
====================================
Hinglish: Scene state (structured, ContextManager se) + Visual
Observation (vision se) — dono ko combine karta hai. Agent ko sirf
IMAGE nahi milta, aur sirf SCENE DATA bhi nahi — dono ek saath,
taaki Agent reason kar sake: "scene kehti hai cube exist karta hai,
vision kehti hai cube badly framed hai."
"""

from dataclasses import dataclass, field
from typing import Any, Dict

from .models import VisualObservation


@dataclass
class SceneVisionContext:
    """Hinglish: Ek combined snapshot — structured state + visual understanding."""
    scene_context: Dict[str, Any] = field(default_factory=dict)
    visual_observation: VisualObservation = None

    def has_visual_data(self) -> bool:
        return self.visual_observation is not None


class VisionContextManager:

    def __init__(self, context_manager, vision_analyzer):
        # Dependency Injection — Phase 3 ka ContextManager + Phase 5 ka VisionAnalyzer
        self._context_manager = context_manager
        self._vision_analyzer = vision_analyzer

    def build_context(self, filepath: str, focus_object_names=None) -> SceneVisionContext:
        scene_context = self._context_manager.build_context(focus_object_names=focus_object_names)
        observation = self._vision_analyzer.observe(filepath=filepath, context=scene_context)

        return SceneVisionContext(
            scene_context=scene_context,
            visual_observation=observation,
        )