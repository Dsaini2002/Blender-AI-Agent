"""
image_paths.py
===============
Hinglish: Render aur vision ko ek hi file ke baare mein baat karni hoti hai. Windows par ye toot jaata tha:

    Gemini ne bheja:        /tmp/room_preview.png
    Blender ne save kiya:   C:\tmp\room_preview.png          (Blender ke drive par)
    Python ne dhoondha:     D:\tmp\room_preview.png          (Python ke current drive par)  -> Errno 2

Is module ka `resolve_image_path` har tool/bridge ke liye EK hi, poora (absolute), drive-wala path banata hai,
taaki render kahan likhe aur vision kahan padhe — dono ek jagah dekhein. Sirf standard library.

Rules (Windows):
  C:\\a\\b.png, D:/a/b.png   -> jaisa hai waisa (asli drive path)
  \\\\server\\share\\b.png     -> jaisa hai waisa (network path)
  /tmp/b.png, \\tmp\\b.png, ~/b.png, //b.png, a/b.png, b.png  ->  <Temp folder>\\b.png
Linux/Mac: asli absolute paths jaise hain; ~ expand hota hai; relative/bare -> <Temp>/naam.
Extension na ho to .png jod diya jaata hai.
"""

import os
import posixpath
import struct
import tempfile
from typing import Dict, Optional

_IMAGE_FORMATS = {
    ".png": "PNG", ".jpg": "JPEG", ".jpeg": "JPEG", ".bmp": "BMP",
    ".tif": "TIFF", ".tiff": "TIFF", ".exr": "OPEN_EXR",
}
_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def image_format_for(path: str) -> str:
    """File ke extension se Blender ka file_format ('PNG', 'JPEG', ...). Anjaan extension -> PNG."""
    return _IMAGE_FORMATS.get(os.path.splitext(path)[1].lower(), "PNG")


def _has_drive(text: str) -> bool:
    return len(text) >= 2 and text[1] == ":" and text[0].isalpha()


def _basename(text: str, default_name: str) -> str:
    normalized = text.replace("\\", "/")
    if normalized.endswith("/"):            # "/tmp/" = sirf folder, file ka naam nahi
        return default_name
    return posixpath.basename(normalized) or default_name


def resolve_image_path(path: Optional[str], default_name: str = "preview.png", windows: Optional[bool] = None) -> str:
    """Kisi bhi image path ko ek pakka absolute path mein badalta hai (upar ke rules)."""
    if windows is None:
        windows = os.name == "nt"

    text = (path or "").strip().strip('"').strip("'")
    temp = tempfile.gettempdir()

    if not text:
        resolved = os.path.join(temp, default_name)
    elif windows:
        if _has_drive(text) or text.startswith("\\\\"):
            resolved = os.path.normpath(text)
        else:                                   # rooted ('/tmp/x'), '~', '//x', relative, bare -> Temp
            resolved = os.path.join(temp, _basename(text, default_name))
    else:
        if text.startswith("~"):
            text = os.path.expanduser(text)
        if os.path.isabs(text):
            resolved = os.path.normpath(text)
        else:
            resolved = os.path.join(temp, _basename(text, default_name))

    if os.path.splitext(resolved)[1].lower() not in _IMAGE_FORMATS:
        resolved += ".png"
    return resolved


def describe_image(path: str) -> Dict[str, int]:
    """
    Render ka "saboot": file asal mein bani ya nahi, kitni badi hai, aur (PNG ke liye) kitne pixel.
    File na ho (ya padh na sake) to khaali dict — tools ka purana output tab bilkul nahi badalta.
    """
    try:
        if not path or not os.path.isfile(path):
            return {}
        info: Dict[str, int] = {"size_bytes": os.path.getsize(path)}
        with open(path, "rb") as handle:
            header = handle.read(24)
        if header[:8] == _PNG_SIGNATURE and len(header) >= 24:
            width, height = struct.unpack(">II", header[16:24])
            info.update({"width": width, "height": height})
        return info
    except OSError:
        return {}