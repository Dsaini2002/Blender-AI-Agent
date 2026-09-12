from . import _bpy_stub  # noqa: F401

import unittest

from blender_ai_agent.observability.tracer import Tracer


class TestTracer(unittest.TestCase):

    def test_single_span(self):
        tracer = Tracer()
        tracer.start_span("Task")
        tracer.end_span()

        trace = tracer.get_trace()
        self.assertEqual(len(trace), 1)
        self.assertEqual(trace[0].name, "Task")

    def test_nested_spans(self):
        tracer = Tracer()
        tracer.start_span("Task")
        tracer.start_span("Modeling")
        tracer.start_span("Tool 1")
        tracer.end_span()
        tracer.end_span()
        tracer.end_span()

        trace = tracer.get_trace()
        self.assertEqual(trace[0].name, "Task")
        self.assertEqual(trace[0].children[0].name, "Modeling")
        self.assertEqual(trace[0].children[0].children[0].name, "Tool 1")

    def test_multiple_children_at_same_level(self):
        tracer = Tracer()
        tracer.start_span("Task")
        tracer.start_span("Modeling")
        tracer.end_span()
        tracer.start_span("Material")
        tracer.end_span()
        tracer.end_span()

        task_span = tracer.get_trace()[0]
        child_names = [c.name for c in task_span.children]
        self.assertEqual(child_names, ["Modeling", "Material"])

    def test_render_tree_indentation(self):
        tracer = Tracer()
        tracer.start_span("Task")
        tracer.start_span("Modeling")
        tracer.end_span()
        tracer.end_span()

        text = tracer.render_tree()
        self.assertIn("Task", text)
        self.assertIn("  Modeling", text)


if __name__ == "__main__":
    unittest.main()