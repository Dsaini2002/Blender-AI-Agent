"""Advanced Skill Permission Checking"""

from ..tools.base import Permission


class SkillPermissionChecker:

    def __init__(self, tool_registry):
        self._tool_registry = tool_registry

    def requires_confirmation(self, skill) -> bool:
        return skill.has_destructive_operations(self._tool_registry)

    def highest_permission(self, skill) -> Permission:
        permissions = [
            self._tool_registry.get(name).permission
            for name in skill.required_permissions(self._tool_registry)
        ]

        if not permissions:
            return Permission.READ_ONLY

        risk_order = [Permission.READ_ONLY, Permission.SAFE_WRITE, Permission.DESTRUCTIVE]
        return max(permissions, key=risk_order.index) 