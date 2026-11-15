"""StressTest"""

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
        for result in results:
            if result.object_count == 0:
                continue
            per_object = result.duration_seconds / result.object_count
            if per_object > max_duration_per_object:
                return False
        return True