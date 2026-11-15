"""Planner"""

from dataclasses import dataclass, field
from typing import List

from .models import ModelResponse, ToolCall


@dataclass
class PlanStep:
    tool_call: ToolCall


@dataclass
class Plan:
    steps: List[PlanStep] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return len(self.steps) == 0


class Planner:

    def create_plan(self, response: ModelResponse) -> Plan:
        steps = [PlanStep(tool_call=tc) for tc in response.tool_calls]
        return Plan(steps=steps)