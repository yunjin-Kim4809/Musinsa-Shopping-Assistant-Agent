"""토큰 버킷 rate limiter 테스트."""

import pytest

from app.infra.rate_limiter import TokenBucket


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


def make_bucket(rate=2.0, capacity=4.0):
    clock = FakeClock()
    sleeps = []

    def fake_sleep(seconds):
        sleeps.append(seconds)
        clock.advance(seconds)  # sleep하면 그만큼 시간이 흐른 것으로 처리

    bucket = TokenBucket(rate=rate, capacity=capacity, clock=clock, sleep=fake_sleep)
    return bucket, clock, sleeps


def test_초기_버스트는_용량만큼_허용():
    bucket, _, _ = make_bucket(rate=2.0, capacity=4.0)
    for _ in range(4):
        assert bucket.try_acquire() is True
    assert bucket.try_acquire() is False  # 버킷 고갈


def test_시간이_지나면_리필():
    bucket, clock, _ = make_bucket(rate=2.0, capacity=4.0)
    for _ in range(4):
        bucket.try_acquire()

    clock.advance(1.0)  # 2 토큰 리필
    assert bucket.try_acquire() is True
    assert bucket.try_acquire() is True
    assert bucket.try_acquire() is False


def test_리필은_용량을_초과하지_않음():
    bucket, clock, _ = make_bucket(rate=2.0, capacity=4.0)
    clock.advance(100.0)  # 아무리 오래 지나도
    assert bucket.available_tokens == 4.0


def test_acquire는_필요한_만큼만_대기():
    bucket, _, sleeps = make_bucket(rate=2.0, capacity=4.0)
    for _ in range(4):
        bucket.try_acquire()

    # 토큰 0개 상태에서 1개 필요 → 0.5초 대기 후 성공해야 함
    assert bucket.acquire(1) is True
    assert len(sleeps) == 1
    assert sleeps[0] == pytest.approx(0.5)


def test_acquire_타임아웃():
    bucket, _, _ = make_bucket(rate=0.1, capacity=1.0)
    bucket.try_acquire()  # 고갈 (리필에 10초 필요)
    assert bucket.acquire(1, timeout=1.0) is False


def test_용량_초과_요청은_에러():
    bucket, _, _ = make_bucket(rate=1.0, capacity=2.0)
    with pytest.raises(ValueError):
        bucket.acquire(3)


def test_잘못된_인자():
    with pytest.raises(ValueError):
        TokenBucket(rate=0, capacity=1)
    with pytest.raises(ValueError):
        TokenBucket(rate=1, capacity=0)
