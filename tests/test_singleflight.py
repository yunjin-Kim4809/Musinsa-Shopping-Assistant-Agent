"""Singleflight 패턴 테스트: 동시 호출 병합, 예외 공유, 캐시 스탬피드 방지."""

import threading

from app.infra.cache import TTLLRUCache
from app.infra.circuit_breaker import CircuitBreaker
from app.infra.rate_limiter import TokenBucket
from app.infra.search_client import TavilySearchClient
from app.infra.singleflight import SingleFlight


def test_순차_호출은_각각_실행():
    sf = SingleFlight()
    calls = []

    def fn():
        calls.append(1)
        return len(calls)

    assert sf.do("k", fn) == 1
    assert sf.do("k", fn) == 2  # flight 종료 후 새 호출은 새로 실행
    assert sf.in_flight_count() == 0


def test_동시_호출은_한_번만_실행되고_결과_공유():
    sf = SingleFlight()
    started = threading.Event()
    release = threading.Event()
    call_count = []
    results = []

    def slow_fn():
        call_count.append(1)
        started.set()
        release.wait(timeout=5)
        return "리더의 결과"

    def worker():
        results.append(sf.do("같은키", slow_fn))

    leader = threading.Thread(target=worker)
    leader.start()
    assert started.wait(timeout=5)  # 리더가 fn 진입할 때까지 대기

    followers = [threading.Thread(target=worker) for _ in range(5)]
    for t in followers:
        t.start()

    release.set()
    leader.join(timeout=5)
    for t in followers:
        t.join(timeout=5)

    assert len(call_count) == 1  # 6개 스레드, 실행은 1회
    assert results == ["리더의 결과"] * 6


def test_리더의_예외를_팔로워도_공유():
    sf = SingleFlight()
    started = threading.Event()
    release = threading.Event()
    errors = []

    def failing_fn():
        started.set()
        release.wait(timeout=5)
        raise RuntimeError("리더 실패")

    def worker():
        try:
            sf.do("k", failing_fn)
        except RuntimeError as exc:
            errors.append(str(exc))

    leader = threading.Thread(target=worker)
    leader.start()
    started.wait(timeout=5)

    follower = threading.Thread(target=worker)
    follower.start()
    release.set()
    leader.join(timeout=5)
    follower.join(timeout=5)

    assert errors == ["리더 실패", "리더 실패"]
    assert sf.in_flight_count() == 0


def test_다른_키는_독립적으로_실행():
    sf = SingleFlight()
    calls = []

    sf.do("a", lambda: calls.append("a"))
    sf.do("b", lambda: calls.append("b"))
    assert calls == ["a", "b"]


class SlowTransport:
    """모든 검색이 release 이벤트까지 블로킹되는 가짜 전송 계층."""

    def __init__(self):
        self.calls = []
        self.started = threading.Event()
        self.release = threading.Event()
        self._lock = threading.Lock()

    def search(self, query, search_depth, max_results):
        with self._lock:
            self.calls.append(query)
        self.started.set()
        self.release.wait(timeout=5)
        return {"results": [{"title": query, "url": f"https://m.com/{query}", "content": "c"}]}


def test_캐시_스탬피드_방지_통합():
    """동일 쿼리의 동시 요청 N개 → 원격 호출은 정확히 1회."""
    transport = SlowTransport()
    client = TavilySearchClient(
        transport=transport,
        cache=TTLLRUCache(max_size=16, ttl=60),
        bucket=TokenBucket(rate=1000, capacity=1000),
        breaker=CircuitBreaker(failure_threshold=3),
        retry_base_delay=0.0,
        retry_max_delay=0.0,
    )

    results = []
    threads = [
        threading.Thread(target=lambda: results.append(client.search("나이키")))
        for _ in range(8)
    ]
    threads[0].start()
    assert transport.started.wait(timeout=5)  # 리더가 원격 호출 진입
    for t in threads[1:]:
        t.start()

    transport.release.set()
    for t in threads:
        t.join(timeout=5)

    assert len(transport.calls) == 1  # 8개 요청, 원격 호출 1회
    assert len(results) == 8
    assert all(r[0].title == "나이키" for r in results)

    # flight 종료 후에는 캐시가 결과를 서빙
    client.search("나이키")
    assert len(transport.calls) == 1
