"""Colour words -> RGB (0-1), so 'make the walls sky blue' or 'roof laal karo' work without the model guessing numbers."""

import re
from typing import List, Optional

NAMED = {
    "white": (0.92, 0.92, 0.9), "off white": (0.9, 0.88, 0.82), "cream": (0.93, 0.88, 0.74), "ivory": (0.95, 0.93, 0.84),
    "beige": (0.85, 0.77, 0.62), "sand": (0.82, 0.72, 0.52), "tan": (0.72, 0.58, 0.4), "khaki": (0.74, 0.69, 0.5),
    "black": (0.03, 0.03, 0.03), "charcoal": (0.12, 0.12, 0.13), "dark grey": (0.2, 0.2, 0.21), "dark gray": (0.2, 0.2, 0.21),
    "grey": (0.5, 0.5, 0.5), "gray": (0.5, 0.5, 0.5), "light grey": (0.75, 0.75, 0.75), "light gray": (0.75, 0.75, 0.75),
    "silver": (0.75, 0.76, 0.78), "red": (0.75, 0.08, 0.06), "dark red": (0.4, 0.04, 0.04), "maroon": (0.4, 0.05, 0.08),
    "crimson": (0.7, 0.05, 0.12), "brick red": (0.55, 0.2, 0.12), "terracotta": (0.62, 0.3, 0.18), "rust": (0.55, 0.25, 0.1),
    "orange": (0.95, 0.42, 0.05), "peach": (0.98, 0.72, 0.56), "coral": (0.95, 0.45, 0.35), "salmon": (0.95, 0.55, 0.45),
    "yellow": (0.95, 0.82, 0.1), "golden": (0.83, 0.65, 0.3), "gold": (0.83, 0.65, 0.3), "mustard": (0.8, 0.62, 0.1),
    "lemon": (0.98, 0.92, 0.35), "green": (0.12, 0.5, 0.15), "dark green": (0.05, 0.25, 0.08), "light green": (0.5, 0.8, 0.45),
    "olive": (0.45, 0.45, 0.15), "lime": (0.55, 0.85, 0.15), "mint": (0.6, 0.9, 0.75), "sage": (0.6, 0.68, 0.55),
    "emerald": (0.05, 0.55, 0.3), "teal": (0.0, 0.45, 0.45), "turquoise": (0.2, 0.78, 0.75), "cyan": (0.1, 0.8, 0.85),
    "blue": (0.08, 0.25, 0.75), "dark blue": (0.03, 0.08, 0.35), "navy": (0.03, 0.06, 0.25), "navy blue": (0.03, 0.06, 0.25),
    "sky blue": (0.45, 0.7, 0.92), "light blue": (0.6, 0.78, 0.95), "royal blue": (0.1, 0.2, 0.7), "indigo": (0.2, 0.1, 0.5),
    "purple": (0.42, 0.12, 0.55), "violet": (0.55, 0.3, 0.8), "lavender": (0.75, 0.68, 0.9), "magenta": (0.85, 0.1, 0.6),
    "pink": (0.95, 0.55, 0.68), "hot pink": (0.95, 0.25, 0.55), "rose": (0.85, 0.4, 0.5), "brown": (0.38, 0.22, 0.1),
    "dark brown": (0.2, 0.11, 0.05), "light brown": (0.6, 0.42, 0.25), "chocolate": (0.3, 0.16, 0.07), "walnut": (0.3, 0.18, 0.1),
    "wood": (0.5, 0.32, 0.17), "copper": (0.72, 0.45, 0.2), "bronze": (0.55, 0.38, 0.18),
    # Hindi / Hinglish
    "safed": (0.92, 0.92, 0.9), "kala": (0.03, 0.03, 0.03), "kaala": (0.03, 0.03, 0.03), "laal": (0.75, 0.08, 0.06),
    "lal": (0.75, 0.08, 0.06), "neela": (0.08, 0.25, 0.75), "nila": (0.08, 0.25, 0.75), "peela": (0.95, 0.82, 0.1),
    "pila": (0.95, 0.82, 0.1), "hara": (0.12, 0.5, 0.15), "gulabi": (0.95, 0.55, 0.68), "narangi": (0.95, 0.42, 0.05),
    "bhura": (0.38, 0.22, 0.1), "aasmani": (0.45, 0.7, 0.92), "sunehra": (0.83, 0.65, 0.3), "baingani": (0.42, 0.12, 0.55),
}


def parse_color(value, what: str = "color") -> Optional[List[float]]:
    """[r, g, b] / [r, g, b, a] (0-1 or 0-255), '#rrggbb', 'r,g,b' or a colour word -> [r, g, b, 1.0]."""
    if value is None or value == "":
        return None
    if isinstance(value, str):
        text = value.strip().lower().replace("_", " ").replace("-", " ")
        text = re.sub(r"\s+", " ", text)
        if re.fullmatch(r"#?[0-9a-f]{6}", text):
            text = text.lstrip("#")
            return [round(int(text[i:i + 2], 16) / 255.0, 4) for i in (0, 2, 4)] + [1.0]
        if text.startswith("[") or re.fullmatch(r"[\d.,\s]+", text):
            value = [float(x) for x in re.findall(r"[\d.]+", text)]
        else:
            if text in NAMED:
                return list(NAMED[text]) + [1.0]
            words = text.replace(" colour", "").replace(" color", "").replace(" rang", "").strip()
            if words in NAMED:
                return list(NAMED[words]) + [1.0]
            shade = re.match(r"(light|pale|pastel|soft|halka|dark|deep|gehra|bright)\s+(.+)$", words)
            if shade and shade.group(2) in NAMED:
                base = NAMED[shade.group(2)]
                kind = shade.group(1)
                if kind in ("light", "pale", "pastel", "soft", "halka"):
                    mix = 0.65 if kind in ("pale", "pastel") else 0.5
                    rgb = [c + (1.0 - c) * mix for c in base]
                elif kind == "bright":
                    top = max(base) or 1.0
                    rgb = [min(1.0, c / top) for c in base]
                else:
                    rgb = [c * 0.45 for c in base]
                return [round(c, 4) for c in rgb] + [1.0]
            for name in sorted(NAMED, key=len, reverse=True):            # 'a nice dark green' -> dark green
                if re.search(rf"\b{re.escape(name)}\b", words):
                    return list(NAMED[name]) + [1.0]
            raise ValueError(f"unknown {what} '{value}'. Use a colour word (e.g. sky blue, cream, maroon, laal) or [r, g, b]")
    values = [float(v) for v in list(value)]
    if len(values) not in (3, 4):
        raise ValueError(f"{what} must be [r, g, b] (0-1)")
    if max(values[:3]) > 1.0:
        values = [v / 255.0 for v in values[:3]] + values[3:]
    values = [min(1.0, max(0.0, v)) for v in values]
    return (values + [1.0])[:4]
