"""
BenchmarkReporter — Step 8.42
==================================
Hinglish: Human-readable summary banata hai — spec ke exact format
jaisa (headers, category breakdown, reliability, performance).
"""

from .metrics import BenchmarkMetrics


class BenchmarkReporter:

    def generate_report(self, metrics: BenchmarkMetrics, version: str = "1.0") -> str:
        lines = [
            "=" * 40,
            " Blender AI Agent Benchmark",
            "=" * 40,
            "",
            f"Benchmark Version: {version}",
            "",
            f"Tasks: {metrics.total_tasks}",
            f"Overall Success: {metrics.success_rate * 100:.0f}%",
            "",
            "-" * 40,
            " Performance",
            "-" * 40,
            "",
            f"Avg Duration:   {metrics.average_duration:.2f} sec",
            f"Avg Tool Calls: {metrics.average_tool_calls:.1f}",
            f"Avg Retries:    {metrics.average_retries:.1f}",
            f"Rollbacks:      {metrics.total_rollbacks}",
            "",
            "-" * 40,
            " Status Breakdown",
            "-" * 40,
            "",
        ]

        for status, count in sorted(metrics.status_breakdown.items()):
            lines.append(f"{status}: {count}")

        lines.append("=" * 40)
        return "\n".join(lines)