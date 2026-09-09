from . import _bpy_stub  # noqa: F401

import unittest

from blender_ai_agent.reliability.retry import RetryPolicy


class TestRetryPolicy(unittest.TestCase):

    def test_allows_retry_under_limit(self):
        policy = RetryPolicy(max_retries=2)
        self.assertTrue(policy.should_retry(0))
        self.assertTrue(policy.should_retry(1))

    def test_denies_retry_at_limit(self):
        policy = RetryPolicy(max_retries=2)
        self.assertFalse(policy.should_retry(2))

    def test_zero_max_retries_never_retries(self):
        policy = RetryPolicy(max_retries=0)
        self.assertFalse(policy.should_retry(0))


if __name__ == "__main__":
    unittest.main()