from . import _bpy_stub  # noqa: F401

import unittest

from blender_ai_agent.skills.base import Skill, SkillResult
from blender_ai_agent.skills.registry import SkillRegistry


class DummySkill(Skill):
    name = "dummy_skill"

    def execute(self, context):
        return SkillResult.ok()


class TableSkill(Skill):
    name = "create_table"

    def execute(self, context):
        return SkillResult.ok()


class TestSkillRegistry(unittest.TestCase):

    def setUp(self):
        self.registry = SkillRegistry()

    def test_register_and_get(self):
        skill = DummySkill(tool_caller=None)
        self.registry.register(skill)
        self.assertIs(self.registry.get("dummy_skill"), skill)

    def test_duplicate_register_raises(self):
        self.registry.register(DummySkill(tool_caller=None))
        with self.assertRaises(ValueError):
            self.registry.register(DummySkill(tool_caller=None))

    def test_get_missing_raises(self):
        with self.assertRaises(KeyError):
            self.registry.get("does.not.exist")

    def test_list_skills(self):
        self.registry.register(DummySkill(tool_caller=None))
        self.assertIn("dummy_skill", self.registry.list_skills())

    def test_find_best_match(self):
        self.registry.register(TableSkill(tool_caller=None))
        self.registry.register(DummySkill(tool_caller=None))

        best = self.registry.find_best_match("create a table please")

        self.assertEqual(best.name, "create_table")

    def test_find_best_match_below_threshold_returns_none(self):
        self.registry.register(TableSkill(tool_caller=None))

        best = self.registry.find_best_match("completely unrelated request", min_score=0.9)

        self.assertIsNone(best)


if __name__ == "__main__":
    unittest.main()