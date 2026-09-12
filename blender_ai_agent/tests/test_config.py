from . import _bpy_stub  # noqa: F401

import os
import unittest

from blender_ai_agent.config.settings import AgentConfig, PermissionConfig, ProviderConfig


class TestProviderConfig(unittest.TestCase):

    def test_default_config(self):
        config = ProviderConfig()
        self.assertEqual(config.name, "mock")

    def test_get_api_key_reads_from_environment(self):
        os.environ["TEST_API_KEY_XYZ"] = "secret123"
        config = ProviderConfig(api_key_env_var="TEST_API_KEY_XYZ")

        self.assertEqual(config.get_api_key(), "secret123")
        del os.environ["TEST_API_KEY_XYZ"]

    def test_get_api_key_empty_when_no_env_var_set(self):
        config = ProviderConfig(api_key_env_var="")
        self.assertEqual(config.get_api_key(), "")

    def test_get_api_key_missing_from_environment_returns_empty(self):
        config = ProviderConfig(api_key_env_var="DOES_NOT_EXIST_VAR_12345")
        self.assertEqual(config.get_api_key(), "")


class TestAgentConfig(unittest.TestCase):

    def test_default_values(self):
        config = AgentConfig()
        self.assertEqual(config.max_steps, 20)
        self.assertTrue(config.vision_enabled)

    def test_invalid_max_steps_raises(self):
        with self.assertRaises(ValueError):
            AgentConfig(max_steps=0)

    def test_invalid_max_retries_raises(self):
        with self.assertRaises(ValueError):
            AgentConfig(max_retries=-1)

    def test_from_dict_parses_nested_structure(self):
        data = {
            "provider": {"name": "openai", "api_key_env_var": "OPENAI_API_KEY"},
            "model": {"name": "gpt-4", "temperature": 0.2},
            "agent": {"max_steps": 15, "max_retries": 2},
            "permissions": {"python_execution": False, "destructive_write": "confirmation"},
            "vision": {"enabled": False},
        }

        config = AgentConfig.from_dict(data)

        self.assertEqual(config.provider.name, "openai")
        self.assertEqual(config.provider.model_name, "gpt-4")
        self.assertEqual(config.max_steps, 15)
        self.assertFalse(config.vision_enabled)

    def test_from_dict_with_missing_keys_uses_defaults(self):
        config = AgentConfig.from_dict({})
        self.assertEqual(config.max_steps, 20)


class TestPermissionConfig(unittest.TestCase):

    def test_defaults_are_safe(self):
        perms = PermissionConfig()
        self.assertFalse(perms.python_execution_allowed)
        self.assertTrue(perms.destructive_write_requires_confirmation)


if __name__ == "__main__":
    unittest.main()