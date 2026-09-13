"""
SupervisorAgent — Step 11.10 / 11.12
=========================================
Hinglish: Task ko sahi specialized agent ko assign karta hai, sab
results collect karta hai, aur conflicts resolve karta hai (abhi
simple: pehla matching agent jeet jaata hai).

IMPORTANT (spec rule): Ye single-agent execution ke saath BENCHMARK
COMPARABLE hai — same ToolCaller/interface, taaki Phase 8 ka Evaluator
dono architectures ko fairly compare kar sake.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .base_agent import AgentTaskResult, SpecializedAgent


@dataclass
class SupervisionReport:
    subtask_results: List[AgentTaskResult] = field(default_factory=list)
    unassigned_subtasks: List[str] = field(default_factory=list)

    @property
    def all_succeeded(self) -> bool:
        return len(self.unassigned_subtasks) == 0 and all(r.success for r in self.subtask_results)


class SupervisorAgent:

    def __init__(self, specialized_agents: List[SpecializedAgent]):
        self._agents = specialized_agents

    def find_agent(self, subtask_description: str) -> Optional[SpecializedAgent]:
        for agent in self._agents:
            if agent.can_handle(subtask_description):
                return agent
        return None

    def execute_subtask(self, subtask_description: str, context: Dict[str, Any] = None) -> Optional[AgentTaskResult]:
        agent = self.find_agent(subtask_description)
        if agent is None:
            return None
        return agent.execute(subtask_description, context or {})

    def execute_all(self, subtask_descriptions: List[str], context: Dict[str, Any] = None) -> SupervisionReport:
        report = SupervisionReport()

        for description in subtask_descriptions:
            result = self.execute_subtask(description, context)
            if result is None:
                report.unassigned_subtasks.append(description)
            else:
                report.subtask_results.append(result)

        return report