"""지수 백오프 재시도 테스트."""

import pytest

from app.infra.circuit_breaker import CircuitOpenError
from app.infra.retry import compute_backoff, retry


def test_일시적_실패후_성공():
    attempts = []

    @retry(max_attempts=3, sleep=lambda s: None, rng=lambda: 0.5)
    def flaky():
        attempts.append(1)
        if len(attempts) < 3:
            raise ValueError("일시적 오류")
        return "성공"

    assert flaky() == "성공"
    assert len(attempts) == 3


def test_최대_시도_초과시_마지막_예외_전파():
    attempts = []

    @retry(max_attempts=3, sleep=lambda s: None, rng=lambda: 0.5)
    def always_fails():
        attempts.append(1)
        raise ValueError("계속 실패")

    with pytest.raises(ValueError, match="계속 실패"):
        always_fails()
    assert len(attempts) == 3


def test_non_retryable은_즉시_전파():
    attempts = []

    @retry(max_attempts=5, sleep=lambda s: None)
    def circuit_open():
        attempts.append(1)
        raise CircuitOpenError(retry_after=10)

    with pytest.raises(CircuitOpenError):
        circuit_open()
    assert len(attempts) == 1  # 재시도 없음


def test_백오프_상한이_지수적으로_증가():
    sleeps = []

    @retry(
        max_attempts=4,
        base_delay=1.0,
        max_delay=100.0,
        sleep=sleeps.append,
        rng=lambda: 1.0,  # jitter 최대값 → 상한 그대로 관측
    )
    def always_fails():
        raise ValueError()

    with pytest.raises(ValueError):
        always_fails()

    # 상한: 1*2^0=1, 1*2^1=2, 1*2^2=4
    assert sleeps == [1.0, 2.0, 4.0]


def test_백오프는_max_delay를_넘지_않음():
    assert compute_backoff(10, base_delay=1.0, max_delay=8.0, rng=lambda: 1.0) == 8.0


def test_full_jitter는_0과_상한_사이():
    low = compute_backoff(2, base_delay=1.0, max_delay=100.0, rng=lambda: 0.0)
    high = compute_backoff(2, base_delay=1.0, max_delay=100.0, rng=lambda: 1.0)
    assert low == 0.0
    assert high == 4.0


def test_성공하면_재시도_없음():
    sleeps = []

    @retry(max_attempts=3, sleep=sleeps.append)
    def ok():
        return 42

    assert ok() == 42
    assert sleeps == []
