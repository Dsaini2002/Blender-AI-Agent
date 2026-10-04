from . import _bpy_stub  # noqa: F401

import math
import unittest

from blender_ai_agent.agent.tool_caller import ToolCaller
from blender_ai_agent.inspectors.scene_inspector import SceneInspector
from blender_ai_agent.skills.builtins.cartoon_character import CartoonCharacterSkill, parse_character_request
from blender_ai_agent.skills.builtins.library_props import LibraryPropSkill
from blender_ai_agent.skills.registry import SkillRegistry
from blender_ai_agent.tools import character_builder as cb
from blender_ai_agent.tools.character_tools import CharacterCreateTool, CharacterInput
from blender_ai_agent.tools.registry import ToolRegistry
from blender_ai_agent.tools.scene_tools import SceneInspectTool
from .fakes_ext import FakeBridge

_CACHE = {}


def spec(**params):
    """Builder mehnga hai (har character ~3-8 s): same params ko cache karte hain."""
    key = tuple(sorted((k, str(v)) for k, v in params.items()))
    if key not in _CACHE:
        _CACHE[key] = cb.build_character_spec(dict(params, quality="draft"))
    return _CACHE[key]


def part(sp, name):
    return next((p for p in sp["parts"] if p["name"] == name), None)


def names(sp):
    return [p["name"] for p in sp["parts"]]


def bbox(p):
    ox, oy, oz = p["offset"]
    sx, sy, sz = p["scale"]
    xs = [v[0] * sx + ox for v in p["vertices"]]
    ys = [v[1] * sy + oy for v in p["vertices"]]
    zs = [v[2] * sz + oz for v in p["vertices"]]
    return (min(xs), max(xs)), (min(ys), max(ys)), (min(zs), max(zs))


def watertight(faces):
    count = {}
    for f in faces:
        for k in range(len(f)):
            e = tuple(sorted((f[k], f[(k + 1) % len(f)])))
            count[e] = count.get(e, 0) + 1
    return all(c == 2 for c in count.values())


class TestBuilder(unittest.TestCase):

    def test_default_character_has_everything(self):
        sp = spec()
        for expected in ("head", "torso", "hair", "arm_l", "arm_r", "hand_l", "hand_r", "leg_l", "leg_r", "shoe_l", "shoe_r",
                         "eye_l_white", "eye_r_white", "eye_l_iris", "eye_r_pupil", "eye_l_shine", "brow_l", "brow_r", "mouth"):
            self.assertIn(expected, names(sp), expected)
        used = {p["material"] for p in sp["parts"]}
        self.assertTrue(used <= set(sp["materials"]), used - set(sp["materials"]))
        self.assertEqual(sp["lights"], [])

    def test_every_mesh_part_is_valid_and_smooth(self):
        sp = spec(gender="girl", outfit="dress", accessories=["glasses", "cap"], expression="laugh")
        for p in sp["parts"]:
            if p["kind"] == "mesh_data":
                self.assertTrue(p["smooth"], p["name"])
                self.assertGreaterEqual(len(p["vertices"]), 3, p["name"])
                self.assertTrue(all(len(set(f)) == len(f) >= 3 for f in p["faces"]), p["name"])
                self.assertTrue(all(0 <= i < len(p["vertices"]) for f in p["faces"] for i in f), p["name"])
                self.assertTrue(all(math.isfinite(c) for v in p["vertices"] for c in v), p["name"])
            else:
                self.assertGreaterEqual(len(p["points"]), 2, p["name"])

    def test_body_parts_are_closed_solids(self):
        sp = spec()
        for name in ("head", "torso", "hair", "arm_l", "leg_r"):
            self.assertTrue(watertight(part(sp, name)["faces"]), name)

    def test_proportions_chibi_vs_normal(self):
        chibi, normal = spec(style="chibi"), spec(style="normal")
        head_height = lambda sp: bbox(part(sp, "head"))[2][1] - bbox(part(sp, "head"))[2][0]
        self.assertGreater(head_height(chibi), 0.4)                       # sir ~ aadhi oonchai
        self.assertLess(head_height(normal), 0.25)
        top = lambda sp: max(bbox(p)[2][1] for p in sp["parts"] if p["kind"] == "mesh_data")
        self.assertAlmostEqual(top(chibi), 1.0, delta=0.12)
        self.assertAlmostEqual(top(normal), 1.0, delta=0.12)

    def test_character_stands_on_the_ground_and_faces_plus_y(self):
        sp = spec()
        low = min(bbox(p)[2][0] for p in sp["parts"] if p["kind"] == "mesh_data")
        self.assertAlmostEqual(low, 0.0, delta=0.02)
        head_y = bbox(part(sp, "head"))[1]
        eye_y = bbox(part(sp, "eye_l_white"))[1]
        self.assertGreater(eye_y[1], head_y[1] * 0.85)                    # aankhein chehre ki aage (+y) ki satah par
        self.assertGreater(part(sp, "mouth")["points"][0][1], 0.0)
        self.assertGreater(part(sp, "brow_l")["points"][0][1], 0.0)

    def test_face_is_symmetric(self):
        sp = spec()
        l, r = part(sp, "eye_l_white")["offset"], part(sp, "eye_r_white")["offset"]
        self.assertAlmostEqual(l[0], -r[0])
        self.assertAlmostEqual(l[1], r[1])
        self.assertAlmostEqual(l[2], r[2])
        bl, br = part(sp, "brow_l")["points"], part(sp, "brow_r")["points"]
        for a, b in zip(bl, br):
            self.assertAlmostEqual(a[0], -b[0]); self.assertAlmostEqual(a[1], b[1]); self.assertAlmostEqual(a[2], b[2])

    def test_expressions_change_the_face(self):
        def mouth_pts(e): return part(spec(expression=e), "mouth")["points"]
        smile, frown = mouth_pts("happy"), mouth_pts("sad")
        self.assertGreater(smile[0][2], smile[len(smile) // 2][2])        # muskaan: kinare upar, beech neeche (U)
        self.assertLess(frown[0][2], frown[len(frown) // 2][2])           # udaas: kinare neeche (n)
        brow = lambda e: part(spec(expression=e), "brow_l")["points"]
        angry, sad = brow("angry"), brow("sad")
        self.assertLess(angry[0][2], angry[2][2])                         # gussa: andar ka sira neeche
        self.assertGreater(sad[0][2], sad[2][2])                          # udaas: andar ka sira upar
        self.assertGreater(brow("surprised")[1][2], brow("happy")[1][2])  # hairan: bhaunhein upar
        height = lambda e: bbox(part(spec(expression=e), "eye_l_white"))[2]
        sleepy, normal = height("sleepy"), height("happy")
        self.assertLess(sleepy[1] - sleepy[0], (normal[1] - normal[0]) * 0.4)
        self.assertIn("mouth_open", names(spec(expression="laugh")))
        self.assertIn("mouth_open", names(spec(expression="surprised")))
        self.assertTrue(part(spec(expression="surprised"), "mouth")["closed"])
        wink = names(spec(expression="wink"))
        self.assertIn("eye_r_closed", wink)
        self.assertNotIn("eye_r_white", wink)
        self.assertIn("eye_l_white", wink)

    def test_every_expression_hair_style_accessory_and_outfit_builds(self):
        for e in cb.EXPRESSIONS:
            self.assertIn("mouth", names(spec(expression=e)), e)
        for h in cb.HAIR_STYLES:
            sp = spec(hair_style=h)
            self.assertEqual("hair" in names(sp), h != "none", h)
        for a in cb.ACCESSORIES:
            self.assertTrue(any(a in n or (a == "glasses" and n.startswith("glasses")) or (a == "sunglasses" and n.startswith("sunglasses"))
                                for n in names(spec(accessories=[a]))), a)
        self.assertIn("torso", names(spec(outfit="dress")))

    def test_colors_flow_into_materials(self):
        sp = spec(skin="dark", hair_color="blonde", eye_color="green", shirt_color="red", pants_color="black", shoe_color="white",
                  accessory_color="gold")
        m = sp["materials"]
        self.assertEqual(m["skin"]["color"], cb.COLORS["dark"])
        self.assertEqual(m["hair"]["color"], cb.COLORS["blonde"])
        self.assertEqual(m["iris"]["color"], cb.COLORS["green"])
        self.assertEqual(m["shirt"]["color"], cb.COLORS["red"])
        self.assertEqual(m["pants"]["color"], cb.COLORS["black"])
        self.assertEqual(m["accessory"]["color"], cb.COLORS["gold"])
        self.assertEqual(cb.resolve_color([0.1, 0.2, 0.3]), [0.1, 0.2, 0.3])

    def test_gender_defaults(self):
        girl, boy = spec(gender="girl"), spec(gender="boy")
        self.assertEqual(girl["meta"]["hair_style"], "long")
        self.assertEqual(boy["meta"]["hair_style"], "short")
        self.assertEqual(girl["materials"]["shirt"]["color"], cb.COLORS["pink"])
        self.assertEqual(boy["materials"]["shirt"]["color"], cb.COLORS["blue"])
        self.assertIn("lash_l", names(girl))
        self.assertNotIn("lash_l", names(boy))

    def test_bust_only_has_no_limbs(self):
        sp = spec(bust_only=True)
        for gone in ("arm_l", "leg_l", "shoe_l", "hand_l"):
            self.assertNotIn(gone, names(sp))
        for kept in ("head", "torso", "hair", "mouth"):
            self.assertIn(kept, names(sp))

    def test_dress_skirt_is_shorter_than_the_legs_so_shoes_stay_visible(self):
        dress = spec(gender="girl", outfit="dress")
        torso_low = bbox(part(dress, "torso"))[2][0]
        shoe_top = bbox(part(dress, "shoe_l"))[2][1]
        self.assertGreater(torso_low, shoe_top + 0.02)

    def test_bad_values(self):
        for bad in ({"style": "weird"}, {"gender": "alien"}, {"expression": "grumpy"}, {"hair_style": "mullet"},
                    {"accessories": ["monocle"]}, {"quality": "ultra"}, {"skin": "plaid"}):
            with self.assertRaises(ValueError, msg=str(bad)):
                cb.build_character_spec(dict(bad, quality=bad.get("quality", "low")))


class TestInputAndTool(unittest.TestCase):

    def test_input_understands_everyday_words(self):
        data = CharacterInput(name="Raju", style="cute", gender="ladka", expression="smiling", hair_style="curly",
                              accessories="glasses, hat", outfit="skirt", quality="fast", skin="Tan", shirt_color="Red", height="1.5")
        self.assertEqual((data.style, data.gender, data.expression, data.hair_style, data.outfit, data.quality),
                         ("chibi", "boy", "happy", "afro", "dress", "low"))
        self.assertEqual(data.accessories, ["glasses", "beanie"])
        self.assertEqual((data.skin, data.shirt_color, data.height), ("tan", "red", 1.5))

    def test_colours_as_lists_and_strings(self):
        data = CharacterInput(skin=[0.9, 0.7, 0.6], hair_color="0.1, 0.2, 0.3", shirt_color={"r": 1, "g": 0, "b": 0})
        self.assertEqual(data.skin, [0.9, 0.7, 0.6])
        self.assertEqual(data.hair_color, [0.1, 0.2, 0.3])
        self.assertEqual(data.shirt_color, [1.0, 0.0, 0.0])

    def test_bad_input(self):
        for bad in ({"style": "weird"}, {"expression": "grumpy"}, {"accessories": ["monocle"]}, {"height": 0}, {"name": ""}):
            with self.assertRaises(ValueError, msg=str(bad)):
                CharacterInput(**bad)

    def test_tool_places_a_whole_character_facing_the_front_view(self):
        bridge = FakeBridge()
        result = CharacterCreateTool(bridge).execute({"name": "Hero", "gender": "boy", "expression": "angry", "quality": "draft",
                                                      "location": "2, 3, 0", "height": 2})
        self.assertTrue(result.success, result.error)
        self.assertGreater(result.data["object_count"], 20)
        head = bridge.get_object("Hero_head")
        self.assertEqual(head.type, "MESH")
        self.assertTrue(head.shade_smooth)
        rotation = getattr(head, "rotation", None) or head.rotation_euler
        self.assertAlmostEqual(rotation[2], math.radians(180.0), places=6)           # Blender front view ki taraf
        self.assertEqual(head.scale, [2.0, 2.0, 2.0])
        self.assertTrue(any(o.name.startswith("Hero_brow") for o in bridge._objects))
        self.assertEqual(bridge.get_material("Hero_skin_mat").color[:3], cb.COLORS["peach"])

    def test_two_characters_get_their_own_objects(self):
        bridge = FakeBridge()
        tool = CharacterCreateTool(bridge)
        tool.execute({"name": "A", "quality": "draft"})
        tool.execute({"name": "B", "quality": "draft", "bust_only": True, "location": [3, 0, 0]})
        self.assertIsNotNone(bridge.get_object("A_head"))
        self.assertIsNotNone(bridge.get_object("B_head"))
        self.assertIsNone(bridge.get_object("B_leg_l"))

    def test_metadata(self):
        tool = CharacterCreateTool(FakeBridge())
        self.assertEqual(tool.name, "character.create")
        for word in ("CARTOON CHARACTER", "expression", "bust_only", "hair_style", "accessories"):
            self.assertIn(word, tool.description)


class TestTextParser(unittest.TestCase):

    def test_rich_description(self):
        args = parse_character_request("make a cute girl with long blonde hair, blue eyes, a pink dress and glasses, laughing")
        self.assertEqual((args["gender"], args["hair_style"], args["hair_color"], args["eye_color"], args["outfit"], args["shirt_color"],
                          args["expression"]), ("girl", "long", "blonde", "blue", "dress", "pink", "laugh"))
        self.assertEqual(args["accessories"], ["glasses"])

    def test_boy_with_spiky_hair_and_cap(self):
        args = parse_character_request("create an angry boy with spiky red hair, a blue cap, green shirt and black jeans, named Rocky")
        self.assertEqual((args["gender"], args["expression"], args["hair_style"], args["hair_color"], args["shirt_color"], args["pants_color"],
                          args["name"]), ("boy", "angry", "spiky", "red", "green", "black", "Rocky"))
        self.assertEqual((args["accessories"], args["accessory_color"]), (["cap"], "blue"))

    def test_face_only_and_hindi(self):
        self.assertTrue(parse_character_request("make a cartoon face")["bust_only"])
        self.assertTrue(parse_character_request("cartoon head with sunglasses")["bust_only"])
        self.assertFalse("bust_only" in parse_character_request("cartoon character with full body"))
        hindi = parse_character_request("ek ladki cartoon character banao khush")
        self.assertEqual((hindi["gender"], hindi["expression"]), ("girl", "happy"))

    def test_quality_words(self):
        self.assertEqual(parse_character_request("a draft cartoon character")["quality"], "draft")
        self.assertEqual(parse_character_request("quick cartoon boy")["quality"], "low")
        self.assertEqual(parse_character_request("detailed cartoon girl")["quality"], "high")
        self.assertNotIn("quality", parse_character_request("a cartoon girl"))

    def test_unknown_words_are_just_ignored(self):
        self.assertEqual(parse_character_request("make a cartoon character"), {})
        self.assertEqual(parse_character_request(""), {})


class TestSkill(unittest.TestCase):

    def skill(self):
        bridge = FakeBridge()
        registry = ToolRegistry()
        registry.register(CharacterCreateTool(bridge))
        registry.register(SceneInspectTool(SceneInspector(bridge)))
        return CartoonCharacterSkill(ToolCaller(registry)), bridge

    def test_which_requests_it_takes(self):
        skill, _ = self.skill()
        for text in ("make a cartoon character", "create a cute girl character with long blonde hair", "add a cartoon boy",
                     "make a chibi mascot", "I want a happy cartoon face", "ek cartoon character banao", "design a cartoon avatar with glasses"):
            self.assertEqual(skill.can_handle(text), 0.97, text)

    def test_which_it_leaves_to_the_llm(self):
        skill, _ = self.skill()
        for text in ("make a red cube", "add a campfire", "make a car", "make the cartoon character's hair red",
                     "make a cartoon character walking", "animate the character", "create 3 cartoon characters",
                     "make a cartoon boy next to the tent", "change the character", "make a boy", "make a room",
                     "make a cartoon character " + "and so on " * 20):
            self.assertEqual(skill.can_handle(text), 0.0, text)

    def test_builds_the_character_without_llm_and_reports_how_it_understood(self):
        skill, bridge = self.skill()
        result = skill.execute({"task": "make an angry boy with spiky red hair and glasses named Rocky, draft"})
        self.assertTrue(result.success, result.error)
        self.assertEqual(result.data["name"], "Rocky")
        self.assertEqual(result.data["interpreted_as"]["expression"], "angry")
        self.assertIsNotNone(bridge.get_object("Rocky_head"))
        self.assertTrue(any(o.name.startswith("Rocky_glasses") for o in bridge._objects))

    def test_second_character_gets_a_new_name_and_a_free_spot(self):
        skill, bridge = self.skill()
        first = skill.execute({"task": "make a cartoon character draft"})
        second = skill.execute({"task": "make a cartoon character draft"})
        self.assertEqual((first.data["name"], second.data["name"]), ("Character", "Character2"))
        self.assertNotEqual(first.data["location"][:2], second.data["location"][:2])

    def test_registry_routes_here_and_props_do_not_steal_it(self):
        skill, bridge = self.skill()
        props = LibraryPropSkill(skill._tool_caller)
        registry = SkillRegistry()
        registry.register(props)
        registry.register(skill)
        self.assertEqual(registry.find_best_match("make a cartoon character").name, "cartoon_character")
        self.assertEqual(registry.find_best_match("add a lantern").name, "library_props")


if __name__ == "__main__":
    unittest.main()