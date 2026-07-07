"""서킷 브레이커 상태 머신 테스트."""

import pytest

from app.infra.circuit_breaker import CircuitBreaker, CircuitOpenError, CircuitState


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


def failing():
    raise ConnectionError("원격 호출 실패")


def succeeding():
    return "ok"


@pytest.fixture
def setup():
    clock = FakeClock()
    breaker = CircuitBreaker(failure_threshold=3, recovery_timeout=30.0, clock=clock)
    return breaker, clock


def test_초기_상태는_CLOSED(setup):
    breaker, _ = setup
    assert breaker.state is CircuitState.CLOSED


def test_임계값_미만_실패는_통과(setup):
    breaker, _ = setup
    for _ in range(2):
        with pytest.raises(ConnectionError):
            breaker.call(failing)
    assert breaker.state is CircuitState.CLOSED


def test_연속_실패_임계값_도달시_OPEN(setup):
    breaker, _ = setup
    for _ in range(3):
        with pytest.raises(ConnectionError):
            breaker.call(failing)
    assert breaker.state is CircuitState.OPEN

    # OPEN 상태에서는 호출 자체가 차단됨
    with pytest.raises(CircuitOpenError) as exc_info:
        breaker.call(succeeding)
    assert exc_info.value.retry_after > 0


def test_성공하면_실패_카운터_리셋(setup):
    breaker, _ = setup
    for _ in range(2):
        with pytest.raises(ConnectionError):
            breaker.call(failing)
    breaker.call(succeeding)  # 카운터 리셋

    for _ in range(2):
        with pytest.raises(ConnectionError):
            breaker.call(failing)
    assert breaker.state is CircuitState.CLOSED  # 아직 3연속 아님


def test_복구_시간_경과후_HALF_OPEN_프로브_성공시_CLOSED(setup):
    breaker, clock = setup
    for _ in range(3):
        with pytest.raises(ConnectionError):
            breaker.call(failing)

    clock.advance(30.0)
    assert breaker.state is CircuitState.HALF_OPEN

    breaker.call(succeeding)  # 프로브 성공
    assert breaker.state is CircuitState.CLOSED


def test_HALF_OPEN_프로브_실패시_다시_OPEN(setup):
    breaker, clock = setup
    for _ in range(3):
        with pytest.raises(ConnectionError):
            breaker.call(failing)

    clock.advance(30.0)
    with pytest.raises(ConnectionError):
        breaker.call(failing)  # 프로브 실패

    assert breaker.state is CircuitState.OPEN
    with pytest.raises(CircuitOpenError):
        breaker.call(succeeding)


def test_OPEN_유지_시간_동안은_차단(setup):
    breaker, clock = setup
    for _ in range(3):
        with pytest.raises(ConnectionError):
            breaker.call(failing)

    clock.advance(29.9)  # 아직 recovery_timeout 미달
    with pytest.raises(CircuitOpenError):
        breaker.call(succeeding)


def test_snapshot(setup):
    breaker, _ = setup
    snap = breaker.snapshot()
    assert snap["state"] == "closed"
    assert snap["failure_threshold"] == 3
