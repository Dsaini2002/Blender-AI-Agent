"""
TaskGraph — Step 9.3
========================
Hinglish: Sub-tasks ke beech DEPENDENCIES track karta hai —
simple linear list nahi, ek graph. Topological sort se valid
execution order deta hai (dependent tasks apne dependencies ke
BAAD hi chalenge).
"""

from typing import Dict, List

from .decomposer import SubTask


class CyclicDependencyError(Exception):
    pass


class TaskGraph:

    def __init__(self, subtasks: List[SubTask]):
        self._subtasks: Dict[str, SubTask] = {t.id: t for t in subtasks}

    def get(self, task_id: str) -> SubTask:
        return self._subtasks[task_id]

    def independent_tasks(self) -> List[SubTask]:
        """Hinglish: Step 9.26 — koi dependency nahi, potentially parallel-eligible."""
        return [t for t in self._subtasks.values() if not t.depends_on]

    def execution_order(self) -> List[SubTask]:
        """
        Hinglish: Topological sort — Kahn's algorithm. Dependencies
        pehle, dependents baad mein. Cycle mile toh error (invalid graph).
        """
        in_degree = {tid: len(t.depends_on) for tid, t in self._subtasks.items()}
        ready = [tid for tid, deg in in_degree.items() if deg == 0]
        ordered_ids: List[str] = []

        # Hinglish: Dependents ka reverse-lookup — "is task ke complete hone
        # ke baad kaunse tasks ready ho sakte hain"
        dependents: Dict[str, List[str]] = {tid: [] for tid in self._subtasks}
        for tid, t in self._subtasks.items():
            for dep in t.depends_on:
                dependents[dep].append(tid)

        while ready:
            current = ready.pop(0)
            ordered_ids.append(current)

            for dependent_id in dependents[current]:
                in_degree[dependent_id] -= 1
                if in_degree[dependent_id] == 0:
                    ready.append(dependent_id)

        if len(ordered_ids) != len(self._subtasks):
            raise CyclicDependencyError("TaskGraph has a cyclic dependency — cannot determine execution order.")

        return [self._subtasks[tid] for tid in ordered_ids]
    def parallel_groups(self) -> list:
        """
        Hinglish: Step 11.3/11.4 — execution_order() ek FLAT sequence
        deta hai. Ye method tasks ko "levels" mein group karta hai —
        har level ke andar wale tasks EK-DOOSRE se independent hain
        (potentially parallel), lekin level N, level N-1 complete
        hone ke BAAD hi chalega.

        Return: List[List[SubTask]] — outer list = sequential levels,
        inner list = us level ke parallel-eligible tasks.
        """
        ordered = self.execution_order()  # cycle-check bhi ho jaata hai isi call se
        completed_ids = set()
        remaining = list(ordered)
        levels = []

        while remaining:
            current_level = [
                task for task in remaining
                if all(dep in completed_ids for dep in task.depends_on)
            ]
            if not current_level:
                break  # safety — cycle already check ho chuka hai upar, ye theoretically nahi hoga

            levels.append(current_level)
            for task in current_level:
                completed_ids.add(task.id)
            remaining = [t for t in remaining if t not in current_level]

        return levels