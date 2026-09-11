from . import _bpy_stub  # noqa: F401

import unittest

from blender_ai_agent.copilot.events import CopilotEvent, EventBus


class TestEventBus(unittest.TestCase):

    def test_subscriber_receives_published_event(self):
        bus = EventBus()
        received = []

        bus.subscribe(CopilotEvent.TASK_STARTED, lambda payload: received.append(payload))
        bus.publish(CopilotEvent.TASK_STARTED, task_id="t1")

        self.assertEqual(len(received), 1)
        self.assertEqual(received[0].data["task_id"], "t1")

    def test_multiple_subscribers_all_receive(self):
        bus = EventBus()
        calls = []

        bus.subscribe(CopilotEvent.TOOL_COMPLETED, lambda p: calls.append("sub1"))
        bus.subscribe(CopilotEvent.TOOL_COMPLETED, lambda p: calls.append("sub2"))
        bus.publish(CopilotEvent.TOOL_COMPLETED)

        self.assertEqual(calls, ["sub1", "sub2"])

    def test_unrelated_event_not_received(self):
        bus = EventBus()
        received = []

        bus.subscribe(CopilotEvent.TASK_STARTED, lambda p: received.append(p))
        bus.publish(CopilotEvent.TASK_FAILED)

        self.assertEqual(len(received), 0)

    def test_unsubscribe_stops_receiving(self):
        bus = EventBus()
        received = []

        def callback(payload):
            received.append(payload)

        bus.subscribe(CopilotEvent.TASK_STARTED, callback)
        bus.unsubscribe(CopilotEvent.TASK_STARTED, callback)
        bus.publish(CopilotEvent.TASK_STARTED)

        self.assertEqual(len(received), 0)

    def test_publish_with_no_subscribers_does_not_error(self):
        bus = EventBus()
        bus.publish(CopilotEvent.TASK_COMPLETED)  # exception nahi aani chahiye


if __name__ == "__main__":
    unittest.main()