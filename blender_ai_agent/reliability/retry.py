"""
RetryPolicy — Step 4.7
==========================
Hinglish: "Blindly retry karte raho" bad practice hai. Ek controlled
limit chahiye — max_retries ke baad rukna zaroori hai.
"""

from dataclasses import dataclass


@dataclass
class RetryPolicy:
    max_retries: int = 2

    def should_retry(self, retries_so_far: int) -> bool:
        """
        Hinglish: `retries_so_far` = ab tak kitni baar retry ho chuka
        hai (0 = pehli failure ke baad, koi retry nahi hua abhi).
        """
        return retries_so_far < self.max_retries