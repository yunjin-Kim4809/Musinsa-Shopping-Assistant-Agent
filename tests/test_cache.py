"""TTL-LRU 캐시 테스트. 가짜 시계를 주입해 시간 흐름을 결정적으로 제어한다."""

import pytest

from app.infra.cache import TTLLRUCache


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


@pytest.fixture
def clock():
    return FakeClock()


def test_기본_저장_조회(clock):
    cache = TTLLRUCache(max_size=2, ttl=10, clock=clock)
    cache.put("a", 1)
    assert cache.get("a") == 1
    assert cache.get("없는키") is None
    assert cache.get("없는키", default=-1) == -1


def test_용량_초과시_LRU_축출(clock):
    cache = TTLLRUCache(max_size=2, ttl=100, clock=clock)
    cache.put("a", 1)
    cache.put("b", 2)
    cache.put("c", 3)  # a(LRU) 축출

    assert cache.get("a") is None
    assert cache.get("b") == 2
    assert cache.get("c") == 3
    assert cache.stats.evictions == 1


def test_get이_사용_순서를_갱신(clock):
    cache = TTLLRUCache(max_size=2, ttl=100, clock=clock)
    cache.put("a", 1)
    cache.put("b", 2)
    cache.get("a")  # a를 MRU로 이동
    cache.put("c", 3)  # 이제 b가 LRU → 축출

    assert cache.get("a") == 1
    assert cache.get("b") is None
    assert cache.get("c") == 3


def test_put_갱신도_사용_순서를_갱신(clock):
    cache = TTLLRUCache(max_size=2, ttl=100, clock=clock)
    cache.put("a", 1)
    cache.put("b", 2)
    cache.put("a", 10)  # 값 갱신 → a가 MRU
    cache.put("c", 3)  # b 축출

    assert cache.get("a") == 10
    assert cache.get("b") is None


def test_TTL_만료(clock):
    cache = TTLLRUCache(max_size=10, ttl=5, clock=clock)
    cache.put("a", 1)

    clock.advance(4.9)
    assert cache.get("a") == 1

    clock.advance(0.2)  # 총 5.1초 경과
    assert cache.get("a") is None
    assert cache.stats.expirations == 1


def test_통계_집계(clock):
    cache = TTLLRUCache(max_size=10, ttl=5, clock=clock)
    cache.put("a", 1)
    cache.get("a")  # hit
    cache.get("b")  # miss

    assert cache.stats.hits == 1
    assert cache.stats.misses == 1
    assert cache.stats.hit_rate == 0.5


def test_get_or_set(clock):
    cache = TTLLRUCache(max_size=10, ttl=5, clock=clock)
    calls = []

    def factory():
        calls.append(1)
        return "값"

    assert cache.get_or_set("k", factory) == "값"
    assert cache.get_or_set("k", factory) == "값"
    assert len(calls) == 1  # 두 번째는 캐시 적중


def test_len_과_contains(clock):
    cache = TTLLRUCache(max_size=10, ttl=5, clock=clock)
    cache.put("a", 1)
    assert len(cache) == 1
    assert "a" in cache
    assert "b" not in cache


def test_잘못된_인자():
    with pytest.raises(ValueError):
        TTLLRUCache(max_size=0)
    with pytest.raises(ValueError):
        TTLLRUCache(ttl=0)
