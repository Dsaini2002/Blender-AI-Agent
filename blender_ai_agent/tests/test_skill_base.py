from . import _bpy_stub  # noqa: F401

import unittest

from blender_ai_agent.skills.base import Skill, SkillResult


class TestSkillResult(unittest.TestCase):

    def test_ok_result(self):
        result = SkillResult.ok({"x": 1}, steps_completed=["a", "b"])
        self.assertTrue(result.success)
        self.assertEqual(result.steps_completed, ["a", "b"])

    def test_fail_result(self):
        result = SkillResult.fail("something broke", steps_completed=["a"])
        self.assertFalse(result.success)
        self.assertEqual(result.error, "something broke")


class TestSkillBase(unittest.TestCase):

    def test_cannot_instantiate_directly(self):
        with self.assertRaises(TypeError):
            Skill(tool_caller=None)

    def test_subclass_without_execute_fails(self):
        class BrokenSkill(Skill):
            name = "broken"

        with self.assertRaises(TypeError):
            BrokenSkill(tool_caller=None)

    def test_default_can_handle_matches_name_words(self):
        class TableSkill(Skill):
            name = "create_table"

            def execute(self, context):
                return SkillResult.ok()

        skill = TableSkill(tool_caller=None)
        score = skill.can_handle("please create a table for me")

        self.assertGreater(score, 0.0)

    def test_default_validate_checks_success(self):
        class GoodSkill(Skill):
            name = "good"

            def execute(self, context):
                return SkillResult.ok()

        skill = GoodSkill(tool_caller=None)
        self.assertTrue(skill.validate(SkillResult.ok()))
        self.assertFalse(skill.validate(SkillResult.fail("err")))


if __name__ == "__main__":
    unittest.main()