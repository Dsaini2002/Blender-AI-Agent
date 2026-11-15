"""Quota used up -> wait until the SAME AI has tokens again, then go on.

The AI picked in the panel is the only AI a run uses (no switching to another provider). When its quota / rate limit
is used up, the run waits - as long as the provider says (Gemini: "retry in 43744s"), or by probing again every few
minutes when it does not say - and then continues where it stopped. Stop ends the wait at once. The panel shows a
countdown the whole time.
"""

import re
import threading
import time
from typing import Callable, Optional

# probing again when the provider does not say how long: 1, 2, 5, 10 min, then every 15 min
PROBE_STEPS_S = (60.0, 120.0, 300.0, 600.0, 900.0)
MAX_TOTAL_WAIT_S = 26 * 3600.0           # a daily quota resets within a day; after that something else is wrong


def wait_seconds_from(text: str) -> Optional[float]:
    """How long the provider asks to wait, if it says so ('retry in 43744.2s', 'try again in 7.66s', 'retryDelay':
    '34s', 'Please try again in 1m30s', retry-after: 20)."""
    low = (text or "").lower()
    for pattern in (r"retry in ([\d.]+)\s*s", r"try again in ([\d.]+)\s*s", r"retrydelay\"?\s*:\s*\"?([\d.]+)s",
                    r"retry-after\"?\s*[:=]\s*\"?([\d.]+)", r"seconds:\s*(\d+)"):
        found = re.search(pattern, low)
        if found:
            try:
                return float(found.group(1))
            except ValueError:
                pass
    found = re.search(r"try again in (\d+)m([\d.]+)s", low)
    if found:
        return int(found.group(1)) * 60 + float(found.group(2))
    found = re.search(r"try again in (\d+)h(\d+)m", low)
    if found:
        return int(found.group(1)) * 3600 + int(found.group(2)) * 60
    return None


def clock_text(seconds: float) -> str:
    seconds = max(0, int(seconds))
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    if hours:
        return f"{hours}h {minutes:02d}m"
    if minutes:
        return f"{minutes}m {secs:02d}s"
    return f"{secs}s"


class QuotaWaiter:
    """wait(error_text) -> True when it is time to try again, False when Stop was pressed or waiting cannot help."""

    def __init__(self, provider_label: str = "the AI", should_stop: Callable[[], bool] = lambda: False,
                 status: Callable[[str], None] = lambda text: None, clock: Callable[[], float] = time.time,
                 sleep: Optional[Callable[[float], None]] = None):
        self.provider_label = provider_label
        self.should_stop = should_stop
        self.status = status
        self.clock = clock
        self._sleep = sleep
        self.waits = 0
        self.total_waited = 0.0
        self.last_message = ""

    def _pause(self, seconds: float) -> bool:
        """Sleep in small steps; False as soon as Stop is pressed."""
        if self._sleep is not None:
            if self.should_stop():
                return False
            self._sleep(seconds)
            return not self.should_stop()
        stop_event = None
        try:
            from . import activity
            stop_event = activity._stop
        except Exception:  # noqa: BLE001
            stop_event = None
        end = self.clock() + seconds
        while True:
            left = end - self.clock()
            if left <= 0:
                return not self.should_stop()
            if self.should_stop():
                return False
            step = min(1.0, left)
            if isinstance(stop_event, threading.Event):
                if stop_event.wait(step):
                    return False
            else:
                time.sleep(step)

    def wait(self, error_text: str) -> bool:
        from ..reliability.friendly_errors import is_auth_error, too_large_for_plan
        import os
        if os.environ.get("BLENDER_AI_QUOTA_WAIT", "").strip() == "0" and self._sleep is None:
            return False                     # waiting switched off (the test suite)
        if too_large_for_plan(error_text) or is_auth_error(error_text):
            return False                     # waiting can not fix a request that never fits or a bad key
        if self.total_waited >= MAX_TOTAL_WAIT_S:
            return False
        asked = wait_seconds_from(error_text)
        if asked is not None:
            seconds = asked + 5.0
        else:
            seconds = PROBE_STEPS_S[min(self.waits, len(PROBE_STEPS_S) - 1)]
        seconds = min(seconds, MAX_TOTAL_WAIT_S - self.total_waited)
        self.waits += 1
        until = self.clock() + seconds
        resume_at = time.strftime("%H:%M", time.localtime(until))
        self.last_message = (f"{self.provider_label} quota / rate limit is used up - waiting, the run goes on by "
                             f"itself at {resume_at} (press Stop to cancel)")
        # countdown in the panel, refreshed every few seconds
        while True:
            left = until - self.clock()
            if left <= 0:
                break
            self.status(f"Waiting for {self.provider_label} quota: resumes in {clock_text(left)} "
                        f"(at {resume_at}) - Stop cancels")
            if not self._pause(min(5.0, left)):
                return False
        self.total_waited += seconds
        self.status(f"{self.provider_label} quota should be back - trying again")
        return True
