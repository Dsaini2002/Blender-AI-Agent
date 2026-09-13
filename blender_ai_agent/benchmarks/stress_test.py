"""
StressTest — Step 11.24
============================
Hinglish: Bade scenes (100s objects) pe performance measure karta
hai — latency, tool calls, memory nahi (Python-level memory profiling
scope se bahar hai abhi), lekin object-count scaling ka core check.
"""

import time
from dataclasses import dataclass
from typing import Callable, List


@dataclass
class StressTestResult:
    object_count: int
    duration_seconds: float
    tool_calls: int


class StressTest:

    def run(self, object_counts: List[int], scene_builder: Callable[[int], object], task_runner: Callable) -> List[StressTestResult]:
        """
        Hinglish: Har `object_count` ke liye:
          1. `scene_builder(count)` -> ek bridge banata hai with that many objects
          2. `task_runner(bridge)` -> agent chalata hai, (tool_call_count) return karta hai
          3. Duration measure hota hai

        Dependency Injection — ye class khud FakeBridge ya Agent nahi
        jaanti, sirf callables leti hai.
        """
        results = []

        for count in object_counts:
            bridge = scene_builder(count)

            start = time.time()
            tool_call_count = task_runner(bridge)
            duration = time.time() - start

            results.append(StressTestResult(
                object_count=count,
                duration_seconds=duration,
                tool_calls=tool_call_count,
            ))

        return results

    def scales_reasonably(self, results: List[StressTestResult], max_duration_per_object: float = 0.1) -> bool:
        """
        Hinglish: Simple scaling check — duration object_count ke
        roughly proportional honi chahiye, exponential nahi. Agar
        kisi bhi result ka per-object duration threshold se zyada
        hai, scaling problem hai.
        """
        for result in results:
            if result.object_count == 0:
                continue
            per_object = result.duration_seconds / result.object_count
            if per_object > max_duration_per_object:
                return False
        return True