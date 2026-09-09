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
from blender_ai_agent.tools.registry import ToolRegistry
from blender_ai_agent.tools.scene_tools import SceneInspectTool
from blender_ai_agent.vision.analyzer import VisionAnalyzer
from blender_ai_agent.vision.capture import RenderCapture
from blender_ai_agent.vision.context import VisionContextManager
from blender_ai_agent.vision.models import VisualObservation
from blender_ai_agent.vision.providers.mock import MockVisionProvider
from blender_ai_agent.vision.validator import VisualValidator
from .fakes import FakeBridge


class TestVisionIntegratedWithReliabilityLoop(unittest.TestCase):
    """
    Hinglish: Poore Phase 5 ka "real" integration test — spec ke
    5.12 example jaisa: task complete hone ke baad, Agent explicitly
    visual validation bhi kar sakta hai, aur RepairableExecutionLoop
    ke saath side-by-side kaam karta hai.
    """

    def test_task_completes_then_visual_validation_confirms_result(self):
        bridge = FakeBridge()

        registry = ToolRegistry()
        registry.register(CreateObjectTool(bridge))
        inspector = SceneInspector(bridge)
        registry.register(SceneInspectTool(inspector))

        tool_caller = ToolCaller(registry)
        context_manager = ContextManager(registry.get("scene.inspect"))
        planner = Planner()
        recovery = RecoveryManager(tool_caller)
        logger = Logger()

        text_provider = MockProvider(responses=[
            ModelResponse(
                tool_calls=[ToolCall(tool_name="object.create", arguments={"name": "Cube"})],
                finish_reason="tool_calls",
            ),
            ModelResponse(content="Created the cube."),
        ])

        loop = RepairableExecutionLoop(
            model_provider=text_provider,
            tool_caller=tool_caller,
            context_manager=context_manager,
            planner=planner,
            bridge=bridge,
            recovery_manager=recovery,
            logger=logger,
        )

        # Step 1: Normal task execution (Phase 3/4)
        run_result = loop.run("Create a cube")
        self.assertEqual(run_result.stopped_reason, "stop")
        self.assertIsNotNone(bridge.get_object("Cube"))

        # Step 2: Vision-based confirmation (Phase 5) — separate, explicit step
        vision_provider = MockVisionProvider(observations=[
            VisualObservation(description="A cube is visible.", objects_detected=["cube"], confidence=0.95)
        ])
        vision_context_manager = VisionContextManager(
            context_manager,
            VisionAnalyzer(RenderCapture(bridge), vision_provider),
        )
        visual_validator = VisualValidator()

        validation_result = loop.validate_visually(
            filepath="/tmp/confirm.png",
            expected={"required_objects": ["cube"], "min_confidence": 0.7},
            vision_context_manager=vision_context_manager,
            visual_validator=visual_validator,
        )

        self.assertTrue(validation_result.valid)

    def test_visual_validation_can_fail_independently(self):
        bridge = FakeBridge()
        registry = ToolRegistry()
        inspector = SceneInspector(bridge)
        registry.register(SceneInspectTool(inspector))
        tool_caller = ToolCaller(registry)
        context_manager = ContextManager(registry.get("scene.inspect"))

        vision_provider = MockVisionProvider(observations=[
            VisualObservation(description="Nothing here.", objects_detected=[], confidence=0.4)
        ])
        vision_context_manager = VisionContextManager(
            context_manager,
            VisionAnalyzer(RenderCapture(bridge), vision_provider),
        )

        from blender_ai_agent.agent.repair_loop import RepairableExecutionLoop
        loop = RepairableExecutionLoop(
            model_provider=MockProvider(responses=[]),
            tool_caller=tool_caller,
            context_manager=context_manager,
            planner=Planner(),
            bridge=bridge,
            recovery_manager=RecoveryManager(tool_caller),
            logger=Logger(),
        )

        result = loop.validate_visually(
            filepath="/tmp/fail.png",
            expected={"required_objects": ["cube"], "min_confidence": 0.7},
            vision_context_manager=vision_context_manager,
            visual_validator=VisualValidator(),
        )

        self.assertFalse(result.valid)


if __name__ == "__main__":
    unittest.main()