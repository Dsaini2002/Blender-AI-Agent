"""Main-Thread Dispatch — Non-Blocking Copilot Support"""

import queue
import threading

_dispatch_queue = queue.Queue()

_main_thread_id = threading.get_ident()


def is_main_thread() -> bool:
    return threading.get_ident() == _main_thread_id


def run_on_main_thread(func):
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
    processed = 0
    while True:
        try:
            func, result_event, result_box = _dispatch_queue.get_nowait()
        except queue.Empty:
            break

        try:
            result_box["value"] = func()
        except Exception as exc:  # noqa: BLE001 
            result_box["error"] = exc
        finally:
            result_event.set()
            processed += 1

    return processed