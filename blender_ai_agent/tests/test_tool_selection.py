from . import _bpy_stub  # noqa: F401

import unittest
from types import SimpleNamespace

from blender_ai_agent.agent.models import ToolCall
from blender_ai_agent.agent.state import ConversationState
from blender_ai_agent.agent.tool_selection import OPTIONAL_TOOLS, select_tools
from blender_ai_agent.tools.base import ToolResult

ALL = [SimpleNamespace(name=n) for n in ["object.create", "material.assign", "render.preview"] + list(OPTIONAL_TOOLS)]


def names(defs):
    return {d.name for d in defs}


class TestToolSelection(unittest.TestCase):

    def test_plain_request_gets_core_tools_only(self):
        chosen = names(select_tools(ALL, "make a red table with four legs"))
        self.assertTrue({"object.create", "material.assign", "render.preview"} <= chosen)
        self.assertFalse(chosen & set(OPTIONAL_TOOLS))

    def test_specialist_tools_follow_the_request(self):
        self.assertIn("retopology.remesh", names(select_tools(ALL, "remesh this to clean quads")))
        self.assertIn("python.execute", names(select_tools(ALL, "extrude the top face with bmesh")))
        self.assertIn("asset.import_model", names(select_tools(ALL, r"import C:\models\chair.fbx")))
        self.assertIn("mesh.damage", names(select_tools(ALL, "make the vase look broken")))

    def test_tools_used_earlier_stay_available(self):
        self.assertIn("template.build", names(select_tools(ALL, "continue", used=["template.build"])))


class TestCompactToolResults(unittest.TestCase):

    def test_scene_inspect_is_summarised(self):
        state = ConversationState()
        data = {"objects": [{"name": f"Obj{i}", "type": "MESH", "location": [0, 0, 0]} for i in range(3)]}
        state.add_tool_result_message(ToolCall("scene.inspect", {}), ToolResult.ok(data))
        self.assertEqual(state.get_messages()[-1].content, "Tool 'scene.inspect' succeeded: 3 object(s): Obj0, Obj1, Obj2")

    def test_long_results_are_truncated(self):
        state = ConversationState()
        state.add_tool_result_message(ToolCall("x.y", {}), ToolResult.ok({"blob": "a" * 9000}))
        content = state.get_messages()[-1].content
        self.assertLess(len(content), 4200)
        self.assertIn("truncated", content)


if __name__ == "__main__":
    unittest.main()
