import unittest

from blender_ai_agent.copilot.task_splitter import split_task


class TestSplitTask(unittest.TestCase):

    def test_short_or_single_requests_are_not_split(self):
        for text in ("make a campfire", "Create a red cube with a blue sphere on top",
                     "make a red and blue cube", "add a tree. add a rock."):          # sirf 2 hisse < 3
            self.assertEqual(split_task(text), [text.strip()], text)

    def test_empty_input(self):
        self.assertEqual(split_task(""), [])
        self.assertEqual(split_task("   "), [])
        self.assertEqual(split_task(None), [])

    def test_then_phir_and_semicolons(self):
        self.assertEqual(
            split_task("make a campfire then add a tent then place a lantern"),
            ["make a campfire", "add a tent", "place a lantern"])
        self.assertEqual(
            split_task("campfire banao phir tent lagao uske baad lantern rakho"),
            ["campfire banao", "tent lagao", "lantern rakho"])
        self.assertEqual(split_task("make a rock; add a tree; add a bush"), ["make a rock", "add a tree", "add a bush"])

    def test_sentences(self):
        self.assertEqual(split_task("Make a floor. Add four walls! Put a table in the middle? Add a lamp."),
                         ["Make a floor", "Add four walls", "Put a table in the middle", "Add a lamp"])

    def test_numbered_and_bulleted_lists(self):
        inline = "1) make a floor 2) add walls 3) add a table"
        self.assertEqual(split_task(inline), ["make a floor", "add walls", "add a table"])
        multiline = "1. make a floor\n2. add walls\n3. add a table"
        self.assertEqual(split_task(multiline), ["make a floor", "add walls", "add a table"])
        bullets = "- make a floor\n- add walls\n* add a table\n• add a lamp"
        self.assertEqual(split_task(bullets), ["make a floor", "add walls", "add a table", "add a lamp"])

    def test_plain_lines(self):
        self.assertEqual(split_task("make a floor\nadd walls\nadd a table"), ["make a floor", "add walls", "add a table"])

    def test_fir_tree_is_not_a_connector(self):
        self.assertEqual(split_task("make a fir tree then add a rock then add a tent"),
                         ["make a fir tree", "add a rock", "add a tent"])

    def test_and_alone_does_not_split(self):
        text = "make a red cube and a blue sphere and a green cone"
        self.assertEqual(split_task(text), [text])

    def test_decimals_and_units_are_not_sentence_ends(self):
        parts = split_task("make a cube 2.5 m wide then add a sphere then add a cone")
        self.assertEqual(parts, ["make a cube 2.5 m wide", "add a sphere", "add a cone"])

    def test_leading_and_trailing_noise_is_cleaned(self):
        parts = split_task("make a floor, and then add walls, and then add a table.")
        self.assertEqual(parts, ["make a floor", "add walls", "add a table"])

    def test_tiny_fragments_are_merged_not_run_alone(self):
        parts = split_task("make a floor. ok. add walls. add a table. add a lamp.")
        self.assertEqual(parts, ["make a floor ok", "add walls", "add a table", "add a lamp"])

    def test_max_parts_merges_neighbours(self):
        text = "\n".join(f"add object number {i}" for i in range(1, 13))
        parts = split_task(text, max_parts=5)
        self.assertLessEqual(len(parts), 5)
        self.assertEqual(" ".join(parts).split(), " ".join(f"add object number {i}" for i in range(1, 13)).split())

    def test_min_parts_is_configurable(self):
        text = "make a rock then add a tree"
        self.assertEqual(split_task(text), [text])
        self.assertEqual(split_task(text, min_parts=2), ["make a rock", "add a tree"])

    def test_order_is_preserved(self):
        parts = split_task("first make a floor then add walls then add a table then add a lamp")
        self.assertEqual(parts[1:], ["add walls", "add a table", "add a lamp"])
        self.assertTrue(parts[0].endswith("make a floor"))

    def test_comma_and_and_lists_of_actions_are_split_when_a_verb_follows(self):
        self.assertEqual(
            split_task("make a campfire, add a tent, add a lantern, add a pine tree"),
            ["make a campfire", "add a tent", "add a lantern", "add a pine tree"])
        self.assertEqual(
            split_task("Make a floor, add four walls, add a door, add a table, then add a lamp"),
            ["Make a floor", "add four walls", "add a door", "add a table", "add a lamp"])
        self.assertEqual(split_task("make a cube and rotate it and scale it"),
                         ["make a cube", "rotate it", "scale it"])
        self.assertEqual(split_task("make a floor, and add walls, and add a door"),
                         ["make a floor", "add walls", "add a door"])

    def test_noun_lists_are_never_split_by_commas(self):
        for text in ("make a room with a table, two chairs, a lamp and a rug",
                     "make a red cube, a blue sphere, a green cone and a yellow torus",
                     "add a campfire with logs, stones and flames"):
            self.assertEqual(split_task(text), [text], text)

    def test_two_actions_stay_together_below_min_parts(self):
        text = "make a room, add a table"
        self.assertEqual(split_task(text), [text])
        self.assertEqual(split_task(text, min_parts=2), ["make a room", "add a table"])

    def test_verb_words_inside_names_do_not_split(self):
        text = "create a cube named Lamp, then make it glow orange using emission with strength 5"
        self.assertEqual(split_task(text), [text])                           # only 2 steps


if __name__ == "__main__":
    unittest.main()