"""RetryPolicy"""

from dataclasses import dataclass


@dataclass
class RetryPolicy:
    max_retries: int = 2

    def should_retry(self, retries_so_far: int) -> bool:
        return retries_so_far < self.max_retries