from . import _bpy_stub  # noqa: F401

import unittest

from blender_ai_agent.agent.tool_caller import ToolCaller
from blender_ai_agent.multi_agent.specialized_agents import CameraAgent, MaterialAgent, ModelingAgent
from blender_ai_agent.multi_agent.supervisor import SupervisorAgent
from blender_ai_agent.tools.camera_tools import CreateCameraTool
from blender_ai_agent.tools.material_tools import AssignMaterialTool, CreateMaterialTool
from blender_ai_agent.tools.object_tools import CreateObjectTool
from blender_ai_agent.tools.registry import ToolRegistry
from .fakes import FakeBridge


def build_supervisor():
    bridge = FakeBridge()
    registry = ToolRegistry()
    registry.register(CreateObjectTool(bridge))
    registry.register(CreateMaterialTool(bridge))
    registry.register(AssignMaterialTool(bridge))
    registry.register(CreateCameraTool(bridge))
    tool_caller = ToolCaller(registry)

    agents = [
        ModelingAgent(tool_caller),
        MaterialAgent(tool_caller),
        CameraAgent(tool_caller),
    ]
    return SupervisorAgent(agents), bridge


class TestSpecializedAgents(unittest.TestCase):

    def test_modeling_agent_handles_create_keyword(self):
        supervisor, bridge = build_supervisor()

        result = supervisor.execute_subtask("Create a cube", {"object_name": "Cube"})

        self.assertIsNotNone(result)
        self.assertEqual(result.domain, "modeling")
        self.assertIsNotNone(bridge.get_object("Cube"))

    def test_material_agent_handles_material_keyword(self):
        supervisor, bridge = build_supervisor()
        bridge.create_object(name="Cube")

        result = supervisor.execute_subtask(
            "Add a red material", {"object_name": "Cube", "material_name": "Red", "color": [1, 0, 0]}
        )

        self.assertEqual(result.domain, "material")
        self.assertTrue(result.success)

    def test_camera_agent_handles_camera_keyword(self):
        supervisor, bridge = build_supervisor()

        result = supervisor.execute_subtask("Set up the camera", {"camera_name": "MainCam"})

        self.assertEqual(result.domain, "camera")
        self.assertIsNotNone(bridge.get_object("MainCam"))


class TestSupervisorAgent(unittest.TestCase):

    def test_unassignable_subtask_reported(self):
        supervisor, _ = build_supervisor()

        result = supervisor.execute_subtask("Do something completely unrelated to anything")

        self.assertIsNone(result)

    def test_execute_all_runs_multiple_subtasks(self):
        supervisor, bridge = build_supervisor()

        report = supervisor.execute_all([
            "Create a cube",
            "Set up the camera",
        ], context={"object_name": "Cube", "camera_name": "MainCam"})

        self.assertTrue(report.all_succeeded)
        self.assertEqual(len(report.subtask_results), 2)

    def test_execute_all_reports_unassigned(self):
        supervisor, _ = build_supervisor()

        report = supervisor.execute_all(["Totally unrelated gibberish task"])

        self.assertFalse(report.all_succeeded)
        self.assertEqual(len(report.unassigned_subtasks), 1)


if __name__ == "__main__":
    unittest.main()