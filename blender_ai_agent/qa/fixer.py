"""
GeometryFixer — Step 12.5
=============================
Hinglish: Yehi "Astra" hai — jo detected `Issue`s ko dekh kar
matching Tool call kar deta hai. Har naya auto-fixable issue_type
add karne ke liye bas `_FIX_TOOLS` mapping mein ek entry add karni
hai — naya orchestration code nahi likhna padta (Open/Closed principle,
jaisa `ToolRegistry` ka pattern hai).
"""

from typing import List

from ..tools.geometry_fix_tools import RecalculateNormalsTool, SeparateOverlapTool
from .models import Issue


class GeometryFixer:
    """Har `auto_fixable` Issue ke liye ek matching Tool chalata hai."""

    def __init__(self, bridge):
        self._bridge = bridge
        self._tools = {
            "flipped_normals": RecalculateNormalsTool(bridge),
            "intersecting_geometry": SeparateOverlapTool(bridge),
        }

    def fix(self, issues: List[Issue]) -> List[str]:
        """
        Hinglish: Sirf auto_fixable issues try karta hai. Return value
        un object names ki list hai jinke liye koi fix attempt hua
        (chahe wo fix successful raha ho ya nahi — re-inspection isko
        confirm karegi, yehi loop ka poora point hai).
        """
        attempted: List[str] = []

        for issue in issues:
            if not issue.auto_fixable:
                continue

            tool = self._tools.get(issue.issue_type)
            if tool is None:
                continue  # koi fix-tool registered nahi hai is issue_type ke liye

            tool.execute({"object_name": issue.object_name})
            attempted.append(issue.object_name)

        return attempted
