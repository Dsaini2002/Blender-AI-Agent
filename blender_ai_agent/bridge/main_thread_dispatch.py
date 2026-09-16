"""
Main-Thread Dispatch — Non-Blocking Copilot Support
==========================================================
Hinglish: Blender ka `bpy` API sirf MAIN THREAD pe safe hai. Agar hum
poora Agent (LLM se baat karna + tool execute karna) ek background
thread mein chala dein taaki Blender freeze na ho, to jaise hi wo
thread `bpy.ops.mesh.primitive_cube_add()` jaisa call karega — crash
ya undefined behavior ho sakta hai.

Is module ka kaam: background thread ko ek safe tareeka dena taaki wo
"is chhoti si cheez ko main thread pe chala do" bol sake, apna kaam
rokte hue (worker thread block hota hai, jo theek hai — usse Blender
ki UI freeze nahi hoti), jab tak main thread (Blender ka apna event
loop, TIMER tick ke through) usse process na kar de.

Isse network wait (sabse slow part) background thread mein hoti hai
— UI responsive rehti hai — aur bpy calls (fast) hamesha main thread
pe hi chalte hain (safe).
"""

import queue
import threading

_dispatch_queue = queue.Queue()

# Hinglish: Blender ka main thread hamesha wahi thread hota hai jisme
# addon register() call hua tha — usse yaad rakhte hain taaki hum
# reliably check kar sakein "kya hum abhi main thread pe hain?"
_main_thread_id = threading.get_ident()


def is_main_thread() -> bool:
    return threading.get_ident() == _main_thread_id


def run_on_main_thread(func):
    """
    Hinglish: Background thread se call hota hai. `func` (no-arg
    callable) ko main thread pe chalwata hai, result wapas deta hai
    (ya exception re-raise karta hai). Worker thread yahan BLOCK hota
    hai jab tak main thread isse process na kare — ye safe hai kyunki
    sirf worker thread rukta hai, Blender ki UI nahi.

    Agar already main thread pe hain (jaise unit tests mein, jaha koi
    threading involved hi nahi), seedha call kar dete hain — koi
    queue/wait ki zaroorat nahi.
    """
    if is_main_thread():
        return func()

    result_event = threading.Event()
    result_box = {}
    _dispatch_queue.put((func, result_event, result_box))
    result_event.wait()

    if "error" in result_box:
        raise result_box["error"]
    return result_box.get("value")


def drain_dispatch_queue() -> int:
    """
    Hinglish: Main thread se, Blender ke modal-operator timer se, har
    tick pe call hota hai. Queue mein pending saare requests process
    karta hai (bpy calls yahin, safely, chalte hain), aur kitne
    process hue wo count return karta hai.
    """
    processed = 0
    while True:
        try:
            func, result_event, result_box = _dispatch_queue.get_nowait()
        except queue.Empty:
            break

        try:
            result_box["value"] = func()
        except Exception as exc:  # noqa: BLE001 — worker thread ko exact exception chahiye
            result_box["error"] = exc
        finally:
            result_event.set()
            processed += 1

    return processed