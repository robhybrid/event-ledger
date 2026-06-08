import pytest

from ledger_common.circuit_breaker import CircuitBreaker, CircuitBreakerOpen


@pytest.mark.asyncio
async def test_opens_after_fail_max():
    breaker = CircuitBreaker(fail_max=3, reset_timeout=60)

    async def failing():
        raise RuntimeError("fail")

    for _ in range(3):
        with pytest.raises(RuntimeError):
            await breaker.call(failing)

    with pytest.raises(CircuitBreakerOpen):
        await breaker.call(failing)


@pytest.mark.asyncio
async def test_resets_on_success():
    breaker = CircuitBreaker(fail_max=3, reset_timeout=60)

    async def ok():
        return "ok"

    assert await breaker.call(ok) == "ok"
    breaker.reset()
    assert not breaker.is_open
