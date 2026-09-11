from . import _bpy_stub  # noqa: F401

import unittest
from datetime import datetime, timedelta

from blender_ai_agent.memory.models import Memory
from blender_ai_agent.memory.policies import MemoryPolicy


class TestShouldStore(unittest.TestCase):

    def test_normal_content_should_store(self):
        policy = MemoryPolicy()
        self.assertTrue(policy.should_store("User prefers wood materials."))

    def test_too_short_content_should_not_store(self):
        policy = MemoryPolicy()
        self.assertFalse(policy.should_store("ok"))

    def test_api_key_should_not_store(self):
        policy = MemoryPolicy()
        self.assertFalse(policy.should_store("My api_key is abc123xyz"))

    def test_password_should_not_store(self):
        policy = MemoryPolicy()
        self.assertFalse(policy.should_store("The password is hunter2"))

    def test_token_should_not_store(self):
        policy = MemoryPolicy()
        self.assertFalse(policy.should_store("Here is my auth token: xyz"))


class TestShouldExpire(unittest.TestCase):

    def test_recent_memory_not_expired(self):
        policy = MemoryPolicy(expiry_days=90)
        mem = Memory(content="recent memory")

        self.assertFalse(policy.should_expire(mem))

    def test_old_memory_is_expired(self):
        policy = MemoryPolicy(expiry_days=90)
        mem = Memory(content="old memory")
        mem.created_at = (datetime.now() - timedelta(days=100)).isoformat()

        self.assertTrue(policy.should_expire(mem))

    def test_should_retrieve_false_for_expired(self):
        policy = MemoryPolicy(expiry_days=90)
        mem = Memory(content="old memory")
        mem.created_at = (datetime.now() - timedelta(days=100)).isoformat()

        self.assertFalse(policy.should_retrieve(mem))


if __name__ == "__main__":
    unittest.main()