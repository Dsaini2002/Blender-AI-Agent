"""
Advanced Skill Permission Checking — Step 9.37
====================================================
Hinglish: Phase 7 mein Skill.required_permissions() bana tha —
ab ek dedicated checker jo decide karta hai ki skill ko bina
confirmation ke chalaya ja sakta hai ya nahi, purely permission
logic ke basis pe (Single Responsibility — Skill khud ye decide
nahi karti, ek alag class karti hai).
"""

from ..tools.base import Permission


class SkillPermissionChecker:

    def __init__(self, tool_registry):
        self._tool_registry = tool_registry

    def requires_confirmation(self, skill) -> bool:
        """Hinglish: Skill mein koi DESTRUCTIVE ya PYTHON_EXECUTION-level operation hai?"""
        return skill.has_destructive_operations(self._tool_registry)

    def highest_permission(self, skill) -> Permission:
        """
        Hinglish: Skill ke saare involved tools mein se sabse "risky"
        permission return karta hai — UI ko batane ke liye ki overall
        risk level kya hai.
        """
        permissions = [
            self._tool_registry.get(name).permission
            for name in skill.required_permissions(self._tool_registry)
        ]

        if not permissions:
            return Permission.READ_ONLY

        # Hinglish: Risk order — DESTRUCTIVE sabse zyada risky
        risk_order = [Permission.READ_ONLY, Permission.SAFE_WRITE, Permission.DESTRUCTIVE]
        return max(permissions, key=risk_order.index)