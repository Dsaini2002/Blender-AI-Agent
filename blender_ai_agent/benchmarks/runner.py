"""BenchmarkRunner"""

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
        """Flow: agent.run(instruction) -> evaluate(rules, bridge) -> BenchmarkResult"""
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
        return [self.run_task(task, agent_factory, rules_factory) for task in tasks]