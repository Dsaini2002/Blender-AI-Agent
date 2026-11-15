from . import _bpy_stub  # noqa: F401

import unittest

from blender_ai_agent.agent.context import ContextManager
from blender_ai_agent.agent.models import ModelResponse, ToolCall
from blender_ai_agent.agent.planner import Planner
from blender_ai_agent.agent.repair_loop import RepairableExecutionLoop
from blender_ai_agent.agent.tool_caller import ToolCaller
from blender_ai_agent.inspectors.scene_inspector import SceneInspector
from blender_ai_agent.observability.logger import Logger
from blender_ai_agent.providers.mock_provider import MockProvider
from blender_ai_agent.reliability.recovery import RecoveryManager
from blender_ai_agent.tools.object_tools import CreateObjectTool
from blender_ai_agent.tools.placement_tools import PlaceOnTool, SnapToGroundTool
from blender_ai_agent.tools.registry import ToolRegistry
from blender_ai_agent.tools.scene_tools import SceneInspectTool
from .fakes_ext import FakeBridge


class TestAgentUsesPlacementTools(unittest.TestCase):

    def test_book_ends_up_on_the_table(self):
        bridge = FakeBridge()
        registry = ToolRegistry()
        for tool in (CreateObjectTool(bridge), PlaceOnTool(bridge), SnapToGroundTool(bridge),
                     SceneInspectTool(SceneInspector(bridge))):
            registry.register(tool)
        caller = ToolCaller(registry)
        provider = MockProvider(responses=[
            ModelResponse(tool_calls=[ToolCall("object.create", {"name": "Table", "primitive": "CUBE", "location": [0, 0, 3]}),
                                      ToolCall("object.create", {"name": "Book", "primitive": "CUBE", "location": [5, 5, 9]})]),
            ModelResponse(tool_calls=[ToolCall("object.snap_to_ground", {"names": '["Table"]'}),
                                      ToolCall("object.place_on", {"name": "Book", "target": "Table"})]),
            ModelResponse(content="Book is on the table."),
        ])
        loop = RepairableExecutionLoop(provider, caller, ContextManager(registry.get("scene.inspect")), Planner(),
                                       bridge, RecoveryManager(caller), Logger())
        result = loop.run("put a book on a table")
        self.assertEqual(result.stopped_reason, "stop", result.reply_text)
        self.assertEqual(bridge.get_object("Table").location, [0.0, 0.0, 0.0])
        self.assertEqual(bridge.get_object("Book").location, [0.0, 0.0, 1.0])     # fake box height is 1.0
        sent = {t.name for t in provider.requests[0].tools} if hasattr(provider, "requests") else None
        if sent is not None:
            self.assertIn("object.place_on", sent)


if __name__ == "__main__":
    unittest.main()
