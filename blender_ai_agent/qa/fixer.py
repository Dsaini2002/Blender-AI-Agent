"""GeometryFixer"""

from typing import List

from ..tools.geometry_fix_tools import RecalculateNormalsTool, SeparateOverlapTool
from .models import Issue


class GeometryFixer:

    def __init__(self, bridge):
        self._bridge = bridge
        self._tools = {
            "flipped_normals": RecalculateNormalsTool(bridge),
            "intersecting_geometry": SeparateOverlapTool(bridge),
        }

    def fix(self, issues: List[Issue]) -> List[str]:
        attempted: List[str] = []

        for issue in issues:
            if not issue.auto_fixable:
                continue

            tool = self._tools.get(issue.issue_type)
            if tool is None:
                continue

            tool.execute({"object_name": issue.object_name})
            attempted.append(issue.object_name)

        return attempted
