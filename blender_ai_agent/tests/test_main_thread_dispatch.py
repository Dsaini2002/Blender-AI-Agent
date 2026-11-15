from . import _bpy_stub  # noqa: F401

import threading
import time
import unittest

from blender_ai_agent.bridge import main_thread_dispatch as dispatch


class TestMainThreadDispatch(unittest.TestCase):

    def test_is_main_thread_true_on_test_thread(self):
        self.assertTrue(dispatch.is_main_thread())

    def test_run_on_main_thread_direct_when_already_main(self):
        result = dispatch.run_on_main_thread(lambda: 2 + 2)
        self.assertEqual(result, 4)

    def test_run_on_main_thread_from_worker_thread(self):
        executed_on_thread_id = {}
        results = []
        errors = []

        def target_func():
            executed_on_thread_id["id"] = threading.get_ident()
            return "computed-on-main"

        def worker():
            try:
                value = dispatch.run_on_main_thread(target_func)
                results.append(value)
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)

        worker_thread = threading.Thread(target=worker)
        worker_thread.start()

        deadline = time.time() + 2.0
        while not results and not errors and time.time() < deadline:
            dispatch.drain_dispatch_queue()
            time.sleep(0.005)

        worker_thread.join(timeout=2.0)

        self.assertEqual(results, ["computed-on-main"])
        self.assertEqual(errors, [])
        self.assertEqual(executed_on_thread_id["id"], threading.get_ident())
        self.assertNotEqual(executed_on_thread_id["id"], worker_thread.ident)

    def test_exception_in_worker_call_propagates_back(self):
        errors = []

        def failing_func():
            raise ValueError("boom")

        def worker():
            try:
                dispatch.run_on_main_thread(failing_func)
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)

        worker_thread = threading.Thread(target=worker)
        worker_thread.start()

        deadline = time.time() + 2.0
        while not errors and time.time() < deadline:
            dispatch.drain_dispatch_queue()
            time.sleep(0.005)

        worker_thread.join(timeout=2.0)

        self.assertEqual(len(errors), 1)
        self.assertIsInstance(errors[0], ValueError)
        self.assertEqual(str(errors[0]), "boom")

    def test_drain_dispatch_queue_returns_zero_when_empty(self):
        processed = dispatch.drain_dispatch_queue()
        self.assertEqual(processed, 0)

    def test_multiple_worker_threads_all_get_correct_results(self):
        results = {}

        def worker(n):
            value = dispatch.run_on_main_thread(lambda: n * n)
            results[n] = value

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(5)]
        for t in threads:
            t.start()

        deadline = time.time() + 2.0
        while len(results) < 5 and time.time() < deadline:
            dispatch.drain_dispatch_queue()
            time.sleep(0.005)

        for t in threads:
            t.join(timeout=2.0)

        self.assertEqual(results, {0: 0, 1: 1, 2: 4, 3: 9, 4: 16})


if __name__ == "__main__":
    unittest.main()