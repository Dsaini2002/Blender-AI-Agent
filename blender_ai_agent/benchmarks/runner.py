"""
BenchmarkRunner — Step 8.22 / 8.23 / 8.24
==============================================
Hinglish: Ek task ka poora lifecycle chalata hai (Step 8.3):
    fresh environment -> agent execute -> evaluate -> result

Isolation (8.23): har task apna NAYA bridge/registry leta hai —
kisi task ka state agle task mein leak nahi hota.

Timeout (8.24): agar agent bahut zyada turns le, TIMEOUT status.
"""

import time
from typing import Callable, List

from .models import BenchmarkResult, BenchmarkTask, TaskStatus
from .evaluator import Evaluator


class BenchmarkRunner:

    def __init__(self, evaluator: Evaluator = None):
        self._evaluator = evaluator or Evaluator()

    def run_task(
        self,
        task: BenchmarkTask,
        agent_factory: Callable,
        rules_factory: Callable,
    ) -> BenchmarkResult:
        """
        Hinglish:
          `agent_factory()` -> (agent, bridge) fresh pair banata hai
                                (isolation ke liye — har task naya environment)
          `rules_factory(bridge)` -> is task ke liye ValidationRule list

        Flow: agent.run(instruction) -> evaluate(rules, bridge) -> BenchmarkResult
        """
        start_time = time.time()

        try:
            agent, bridge = agent_factory()
            run_result = agent.run(task.instruction)

            rules = rules_factory(bridge)
            eval_result = self._evaluator.evaluate(task, rules, bridge)

            duration = time.time() - start_time

            return BenchmarkResult(
                task_id=task.id,
                status=eval_result["status"],
                score=eval_result["score"],
                validation_results=eval_result["results"],
                duration=duration,
                tool_calls=getattr(run_result, "tool_call_count", 0),
                retries=getattr(run_result, "repairs_attempted", 0),
                rollbacks=1 if getattr(run_result, "rolled_back", False) else 0,
            )

        except Exception as exc:
            duration = time.time() - start_time
            return BenchmarkResult(
                task_id=task.id,
                status=TaskStatus.ERROR,
                score=0.0,
                errors=[str(exc)],
                duration=duration,
            )

    def run_suite(self, tasks: List[BenchmarkTask], agent_factory: Callable, rules_factory: Callable) -> List[BenchmarkResult]:
        """Hinglish: Multiple tasks ek ke baad ek chalata hai, har ek isolated."""
        return [self.run_task(task, agent_factory, rules_factory) for task in tasks]