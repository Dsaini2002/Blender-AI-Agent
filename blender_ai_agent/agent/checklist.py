"""The checklist: what the request asks to build, written down BEFORE anything is built.

"create a table with two books and a laptop, and a lamp"
    1. table   x1
    2. book    x2   on the table
    3. laptop  x1   on the table
    4. lamp    x1

It is shown to the user first, given to the builder ("build every item, exact counts"), used by the placement step and
checked item by item (with copies counted) by the multi-angle vision check and in the scene itself.
"""

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional

NUMBERS = {"a": 1, "an": 1, "one": 1, "single": 1, "two": 2, "pair": 2, "couple": 2, "three": 3, "four": 4, "five": 5,
           "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "dozen": 12,
           "some": 3, "few": 3, "several": 3}

# things people ask for (singular). The head noun of a clause must be one of them - so "5 m wide" or "modern style"
# never become items.
THINGS = """
table desk chair stool bench sofa couch armchair bed nightstand wardrobe cabinet cupboard drawer dresser shelf bookshelf
bookcase book notebook laptop computer monitor screen keyboard mouse phone tablet printer lamp light chandelier lantern
candle clock mirror painting picture frame poster whiteboard blackboard board rug carpet mat curtain blind window door
plant tree bush flower vase pot cup mug glass bottle plate bowl jar box basket bag tray fan tv television speaker radio
guitar piano ball bat racket net goal hoop car bicycle bike bus truck house hut tent building tower bridge fence gate
wall floor ceiling roof stairs staircase pillar column fountain pool pond rock stone statue sign bin trash can bucket
pillow cushion blanket towel sink toilet bathtub shower fridge refrigerator stove oven microwave kettle counter
coffee_table dining_table study_table table_lamp floor_lamp street_lamp lamp_post pen pencil globe trophy calendar
umbrella hat shoe bottle crate barrel ladder tool hammer sword shield helmet robot rocket plane airplane boat ship
""".split()
PLURALS = {"shelves": "shelf", "bookshelves": "bookshelf", "benches": "bench", "boxes": "box", "glasses": "glass",
           "couches": "couch", "dresses": "dress", "torches": "torch", "brushes": "brush", "people": "person",
           "leaves": "leaf", "knives": "knife", "buses": "bus", "cushions": "cushion", "trees": "tree",
           "dishes": "dish", "watches": "watch", "lunches": "lunch", "mice": "mouse", "stairs": "stairs",
           "glasses_": "glass", "sandwiches": "sandwich", "matches": "match"}
SYNONYMS = {"sofa": ["couch"], "couch": ["sofa"], "tv": ["television", "tv_unit"], "television": ["tv"],
            "bookshelf": ["bookcase", "shelf"], "bookcase": ["bookshelf", "shelf"], "laptop": ["notebook_pc", "computer"],
            "computer": ["monitor", "pc", "laptop"], "rug": ["carpet", "mat"], "carpet": ["rug"], "picture": ["painting", "wall_art", "frame"],
            "painting": ["wall_art", "picture", "frame"], "lamp": ["light", "lantern"], "light": ["lamp"],
            "fridge": ["refrigerator"], "refrigerator": ["fridge"], "bike": ["bicycle"], "bicycle": ["bike"],
            "cupboard": ["cabinet"], "cabinet": ["cupboard"], "plant": ["potted_plant", "bush"], "mug": ["cup"],
            "cup": ["mug"], "staircase": ["stairs", "stair"], "stairs": ["stair", "staircase"]}
SURFACES = re.compile(r"table|desk|counter|shelf|bookshelf|bookcase|nightstand|cabinet|dresser|bed|sofa|tray|stool|bench")
POSITION = re.compile(
    r"\b(on top of|on|onto|upon|next to|beside|besides|near|by|close to|left of|right of|to the left of|to the right of|"
    r"on the left|on the right|behind|in front of|in the front|at the back|under|underneath|below|beneath|above|over|"
    r"inside|in the middle|in the centre|in the center|in the corner|in a corner|against|along|around|between|facing|"
    r"at\s*[\(\[]?\s*-?\d)\b(.*)$", re.IGNORECASE)
VERBS = re.compile(r"^(please\s+)?(create|make|build|add|place|put|design|model|generate|draw|give me|i want|set up|"
                   r"setup|construct|insert|also add|also|then|and|with|plus)\b\s*", re.IGNORECASE)
SPLIT = re.compile(r",|;|\.\s|\n|\bplus\b|\balong with\b|\bas well as\b|\band\b|\bwith\b", re.IGNORECASE)
EDIT = re.compile(r"^\s*(change|recolou?r|colou?r|move|rotate|turn|resize|scale|delete|remove|rename|make (it|the)|"
                  r"replace|swap|fix|undo|hide|shift)\b", re.IGNORECASE)


@dataclass
class Item:
    name: str                       # "table", "book", "glass window"
    count: int = 1
    noun: str = ""                  # the head noun used to find it: "window"
    position: str = ""              # what the user said about where it goes ("on the table") - "" = AI decides
    implied: bool = False           # position comes from "a table WITH two books" (books go on the table)
    at_least: bool = False          # "books" without a number: two or more
    size: str = ""                  # real-world size the planner gave ("0.24 x 0.17 x 0.03 m")
    words: List[str] = field(default_factory=list)

    def label(self) -> str:
        where = f"  ({self.position})" if self.position else ""
        return f"{self.name} x{self.count}{'+' if self.at_least else ''}{where}"


def _singular(word: str) -> str:
    word = word.lower()
    if word in PLURALS:
        return PLURALS[word]
    if word in THINGS:
        return word
    for cut, add in (("ies", "y"), ("es", ""), ("s", "")):
        if word.endswith(cut) and (word[: -len(cut)] + add) in THINGS:
            return word[: -len(cut)] + add
    return word


def _count(words: List[str]) -> int:
    for word in words[:3]:
        if word.isdigit():
            return max(1, min(50, int(word)))
        if word in NUMBERS:
            return NUMBERS[word]
    return 1


def is_edit(request: str) -> bool:
    return bool(EDIT.match(request or ""))


def make_checklist(request: str, extra_things: Optional[List[str]] = None) -> List[Item]:
    """Items the request asks for, in its order, with counts and the positions the user gave."""
    text = (request or "").strip()
    if not text or is_edit(text) or text.startswith("AUTOMATIC CHECK"):
        return []
    known = set(THINGS) | {t.lower() for t in (extra_things or [])}
    items: List[Item] = []
    clauses = []
    # coordinates "(2, 3, 0)" must not be split at their commas
    text = re.sub(r"[\(\[][^\)\]]*[\)\]]", lambda m: m.group(0).replace(",", " "), text)
    # keep which clause came right after "with" (a table WITH two books -> books on the table); ", and" ends it
    pieces = re.split(r"(,|;|\.\s|\n|\bplus\b|\balong with\b|\bas well as\b|\band\b|\bwith\b)", text, flags=re.IGNORECASE)
    after_with = False
    last = ""
    for piece in pieces:
        if piece is None:
            continue
        mark = piece.strip().lower()
        if mark in ("with", "and", "plus", ",", ";", "along with", "as well as") or SPLIT.fullmatch(piece.strip() or "x"):
            if mark == "with":
                after_with = True
            elif mark in (";", "plus", "along with", "as well as") or "\n" in piece or piece.strip() == "." or \
                    (mark == "and" and last == ","):
                after_with = False
            elif mark not in ("and", ","):
                after_with = False
            last = mark if mark else last
            continue
        if not piece.strip():
            continue
        last = ""
        clauses.append((piece.strip(), after_with))
    host: Optional[Item] = None
    for clause, via_with in clauses:
        clause = VERBS.sub("", clause.strip())
        clause = VERBS.sub("", clause)
        position = ""
        match = POSITION.search(clause)
        object_part = clause
        if match:
            position = (match.group(1) + match.group(2)).strip().rstrip(".")
            object_part = clause[: match.start()].strip()
        words = re.findall(r"[a-z0-9_]+", object_part.lower())
        if not words:
            continue
        # the head noun: the last known thing word (handles "two big wooden books", "coffee table")
        head = ""
        head_index = -1
        for index, word in enumerate(words):
            single = _singular(word)
            if single in known:
                head, head_index = single, index
            if index + 1 < len(words) and f"{single}_{_singular(words[index + 1])}" in known:
                head, head_index = f"{single}_{_singular(words[index + 1])}", index + 1
        if not head:
            continue
        count = _count(words)
        plural = words[head_index] != _singular(words[head_index]) and words[head_index] in PLURALS or \
            (words[head_index].endswith("s") and _singular(words[head_index]) != words[head_index])
        at_least = plural and count == 1 and not any(w in NUMBERS or w.isdigit() for w in words[:head_index])
        if at_least:
            count = 2
        if position and host is not None:
            position = re.sub(r"\b(it|them)\b", f"the {host.name}", position)
        adjectives = [w for w in words[:head_index] if w not in NUMBERS and not w.isdigit()
                      and w not in ("the", "of", "small", "big", "large", "nice", "simple", "some", "few")]
        name = " ".join(adjectives[-2:] + [head.replace("_", " ")]) if adjectives else head.replace("_", " ")
        implied = False
        if not position and via_with and host is not None and SURFACES.search(host.noun):
            position, implied = f"on the {host.name}", True
        item = Item(name=name, count=count, noun=head, position=position, implied=implied, at_least=at_least,
                    words=[head] + SYNONYMS.get(head, []))
        # the same thing twice ("a lamp ... and a lamp on the desk") -> one line with the higher count
        same = next((i for i in items if i.noun == item.noun and i.name == item.name), None)
        if same is not None:
            same.count = max(same.count, item.count)
            same.position = same.position or item.position
            continue
        items.append(item)
        if not via_with:
            host = item
        # a new thing named inside the position: "3 chairs around A round dining table"
        introduced = re.search(r"\b(a|an|one)\s+(.*)$", position.lower()) if position else None
        if introduced:
            words_after = re.findall(r"[a-z_]+", introduced.group(2))[:4]
            noun, last = "", -1
            for index, word in enumerate(words_after):
                single = _singular(word)
                if index + 1 < len(words_after) and f"{single}_{_singular(words_after[index + 1])}" in known:
                    noun, last = f"{single}_{_singular(words_after[index + 1])}", index + 1
                    break
                if single in known:
                    noun, last = single, index
            if noun and not any(i.noun == noun for i in items):
                adjectives = [w for w in words_after[:max(0, last - (1 if "_" in noun else 0))]
                              if w not in ("small", "big", "large", "the")]
                extra = Item(name=" ".join(adjectives + [noun.replace("_", " ")]).strip(), count=1, noun=noun,
                             words=[noun] + SYNONYMS.get(noun, []))
                items.append(extra)
                host = extra
    return items[:20]


def checklist_text(items: List[Item]) -> str:
    if not items:
        return ""
    width = max(len(i.name) for i in items)
    lines = []
    for number, item in enumerate(items, 1):
        where = item.position if item.position else "AI decides the best place"
        count = f"x{item.count}{'+' if item.at_least else ''}"
        size = f"  [{item.size}]" if item.size else ""
        lines.append(f"{number:2d}. {item.name.ljust(width)}  {count.ljust(4)} - {where}{size}")
    return "\n".join(lines)


def builder_hint(items: List[Item]) -> str:
    """The system note the builder gets: every item, exact counts, clear names."""
    if not items:
        return ""
    return ("CHECKLIST - build EVERY item below with EXACTLY this many copies (no more, no less). Name each object after "
            "its item (book_1, book_2, laptop ...) so it can be found and checked. Positions given here are the "
            "user's and must be kept:\n" + checklist_text(items))


# ---------------------------------------------------------------------------------------------- finding them
def match_items(items: List[Item], snapshot: dict, parts_by_model: Optional[Dict[str, List[str]]] = None) -> List[dict]:
    """For each checklist item: the copies found in the scene (each copy = its objects + box).
    A copy is one 'thing' (a library model with all its parts, or one object / one name group)."""
    from ..diagnostics.scene_audit import _library_parts, _union, group_items
    objects = {o["name"]: o for o in snapshot.get("objects", []) if o.get("box") and not o.get("hidden")
               and o.get("type") in ("MESH", "CURVE", "SURFACE", "META", "FONT")}
    groups = group_items(sorted(objects), parts_by_model if parts_by_model is not None else _library_parts())
    found = []
    used = set()
    for item in items:
        copies = []
        words = [w.lower() for w in item.words] + [item.noun.replace("_", " "), item.noun]
        for key, group in groups.items():
            if key in used:
                continue
            text = " ".join([key, group.get("model", "")] + group["objects"]).lower()
            materials = " ".join(m for n in group["objects"] for m in (objects[n].get("materials") or []) if m).lower()
            hit = any(re.search(rf"(^|[^a-z]){re.escape(w)}", text) for w in words if w) or \
                (item.noun in ("window", "mirror", "glass") and re.search(r"glass|window", materials))
            if hit:
                copies.append({"key": key, "objects": group["objects"],
                               "box": _union([objects[n]["box"] for n in group["objects"]])})
        # one thing made of many objects named after the item ('table_top', 'table_leg_1'...): one copy, not five
        if len(copies) > item.count:
            merged = _merge_parts(copies, item.noun)
            copies = merged
        for copy in copies:
            used.add(copy["key"])
        found.append({"item": item, "copies": copies})
    return found


PART_WORDS = re.compile(r"(^|_)(top|leg|legs|base|frame|seat|back|arm|arms|shade|stand|pole|bulb|cord|cover|page|pages|"
                        r"spine|screen|keyboard_part|lid|hinge|body|handle|knob|drawer|shelf_board|panel|rim|foot|feet|"
                        r"support|rail|cushion_part|\d+)$")


def _merge_parts(copies: List[dict], noun: str) -> List[dict]:
    """'table_top', 'table_leg_1' ... 'table_leg_4' are ONE table: join copies whose names only differ by a part word."""
    from ..diagnostics.scene_audit import _union
    roots: Dict[str, dict] = {}
    for copy in copies:
        key = copy["key"]
        root = key
        while PART_WORDS.search(root) and "_" in root:
            root = root.rsplit("_", 1)[0]
        root = root.split(".")[0] if root != key.split(".")[0] else root
        entry = roots.setdefault(root, {"key": root, "objects": [], "boxes": []})
        entry["objects"] += copy["objects"]
        entry["boxes"].append(copy["box"])
    return [{"key": r["key"], "objects": r["objects"], "box": _union(r["boxes"])} for r in roots.values()]


def presence_problems(matches: List[dict]) -> List[str]:
    """'book: 1 of 2 found' lines (by name only - the vision check confirms by looking)."""
    out = []
    for entry in matches:
        item, copies = entry["item"], entry["copies"]
        if len(copies) < item.count:
            out.append(f"{item.name}: {len(copies)} of {item.count} found in the scene by name")
    return out
