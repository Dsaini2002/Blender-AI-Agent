"""
Specialized agents — Step 11.11
====================================
Hinglish: Concrete implementations — har ek apne domain ke keywords
pehchanta hai, aur uske relevant tools call karta hai. Simple
keyword-based hai (real LLM-driven decision baad mein isi interface
ke peeche plug hoga).
"""

from typing import Any, Dict

from ..agent.models import ToolCall
from .base_agent import AgentTaskResult, SpecializedAgent


class ModelingAgent(SpecializedAgent):
    domain = "modeling"
    _KEYWORDS = ("create", "cube", "sphere", "object", "body", "shape")

    def can_handle(self, subtask_description: str) -> bool:
        desc = subtask_description.lower()
        return any(kw in desc for kw in self._KEYWORDS)

    def execute(self, subtask_description: str, context: Dict[str, Any]) -> AgentTaskResult:
        name = context.get("object_name", "Object")
        result = self._tool_caller.call(ToolCall(tool_name="object.create", arguments={"name": name}))

        if not result.success:
            return AgentTaskResult(success=False, domain=self.domain, error=result.error)

        return AgentTaskResult(success=True, domain=self.domain, data=result.data)


class MaterialAgent(SpecializedAgent):
    domain = "material"
    _KEYWORDS = ("material", "color", "metallic", "texture", "paint")

    def can_handle(self, subtask_description: str) -> bool:
        desc = subtask_description.lower()
        return any(kw in desc for kw in self._KEYWORDS)

    def execute(self, subtask_description: str, context: Dict[str, Any]) -> AgentTaskResult:
        material_name = context.get("material_name", "Material")
        object_name = context.get("object_name", "Object")
        color = context.get("color")

        create_result = self._tool_caller.call(ToolCall(
            tool_name="material.create",
            arguments={"name": material_name, "color": color} if color else {"name": material_name},
        ))
        if not create_result.success:
            return AgentTaskResult(success=False, domain=self.domain, error=create_result.error)

        assign_result = self._tool_caller.call(ToolCall(
            tool_name="material.assign",
            arguments={"object_name": object_name, "material_name": material_name},
        ))
        if not assign_result.success:
            return AgentTaskResult(success=False, domain=self.domain, error=assign_result.error)

        return AgentTaskResult(success=True, domain=self.domain, data=assign_result.data)


class CameraAgent(SpecializedAgent):
    domain = "camera"
    _KEYWORDS = ("camera", "frame", "render", "composition", "view")

    def can_handle(self, subtask_description: str) -> bool:
        desc = subtask_description.lower()
        return any(kw in desc for kw in self._KEYWORDS)

    def execute(self, subtask_description: str, context: Dict[str, Any]) -> AgentTaskResult:
        camera_name = context.get("camera_name", "Camera")
        result = self._tool_caller.call(ToolCall(tool_name="camera.create", arguments={"name": camera_name}))

        if not result.success:
            return AgentTaskResult(success=False, domain=self.domain, error=result.error)

        return AgentTaskResult(success=True, domain=self.domain, data=result.data)