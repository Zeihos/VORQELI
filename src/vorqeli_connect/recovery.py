"""Bounded, monotonic auto-recovery after an unexpected component failure.

The user's persistent ON/OFF decision always wins. This class has no network,
process or settings side effects; UI tests can exercise it deterministically.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RetryState:
    attempts: int
    max_attempts: int
    next_in_seconds: float | None
    exhausted: bool


class RecoveryPolicy:
    """Retry after delays, never indefinitely or after manual OFF.

    Repeated observations during the same outage do not reset the countdown.
    Each UI application launch starts with a fresh retry budget.
    """

    def __init__(self, delays: tuple[float, ...] = (10, 30, 90)):
        if not delays or any(delay <= 0 for delay in delays):
            raise ValueError('Интервалы восстановления должны быть положительными')
        self.delays = delays
        self.attempts = 0
        self._due: float | None = None

    def reset(self) -> None:
        self.attempts = 0
        self._due = None

    def observe(self, *, wanted: bool, unhealthy: bool, busy: bool, now: float) -> bool:
        """Return True once for each retry due. Never retry while busy."""
        if not wanted or not unhealthy:
            self.reset()
            return False
        if self.attempts >= len(self.delays):
            return False
        if self._due is None:
            self._due = now + self.delays[self.attempts]
            return False
        if busy or now < self._due:
            return False
        self.attempts += 1
        self._due = (now + self.delays[self.attempts]
                     if self.attempts < len(self.delays) else None)
        return True

    def status(self, now: float) -> RetryState:
        wait = None if self._due is None else max(0.0, self._due - now)
        return RetryState(self.attempts, len(self.delays), wait,
                          self.attempts >= len(self.delays))
