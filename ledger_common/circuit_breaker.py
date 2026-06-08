"""Lightweight async-compatible circuit breaker."""

import asyncio
import time
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

T = TypeVar("T")


class CircuitBreakerOpen(Exception):
    """Raised when the circuit breaker is open and calls are rejected."""


class CircuitBreaker:
    def __init__(self, fail_max: int = 5, reset_timeout: float = 30.0):
        self.fail_max = fail_max
        self.reset_timeout = reset_timeout
        self._failures = 0
        self._opened_at: float | None = None
        self._lock = asyncio.Lock()

    @property
    def is_open(self) -> bool:
        if self._opened_at is None:
            return False
        if time.monotonic() - self._opened_at >= self.reset_timeout:
            self._opened_at = None
            self._failures = 0
            return False
        return True

    def record_success(self) -> None:
        self._failures = 0
        self._opened_at = None

    def record_failure(self) -> None:
        self._failures += 1
        if self._failures >= self.fail_max:
            self._opened_at = time.monotonic()

    def reset(self) -> None:
        self._failures = 0
        self._opened_at = None

    async def call(self, func: Callable[..., Awaitable[T]], *args: Any, **kwargs: Any) -> T:
        async with self._lock:
            if self.is_open:
                raise CircuitBreakerOpen("Circuit breaker is open")
        try:
            result = await func(*args, **kwargs)
        except Exception:
            async with self._lock:
                self.record_failure()
            raise
        async with self._lock:
            self.record_success()
        return result
