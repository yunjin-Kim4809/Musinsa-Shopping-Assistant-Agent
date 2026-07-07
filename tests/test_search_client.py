"""검색 클라이언트 테스트: 캐시/재시도/서킷/병렬 조합 동작 검증."""

import pytest

from app.infra.cache import TTLLRUCache
from app.infra.circuit_breaker import CircuitBreaker
from app.infra.rate_limiter import TokenBucket
from app.infra.search_client import (
    SearchUnavailableError,
    TavilySearchClient,
)


class FakeTransport:
    """Tavily SDK 를 흉내내는 가짜 전송 계층."""

    def __init__(self, responses=None, fail_times=0):
        self.calls = []
        self.fail_times = fail_times
        self.responses = responses or {}

    def search(self, query, search_depth, max_results):
        self.calls.append(query)
        if self.fail_times > 0:
            self.fail_times -= 1
            raise ConnectionError("네트워크 오류")
        return self.responses.get(
            query,
            {
                "results": [
                    {
                        "title": f"{query} 결과",
                        "url": f"https://www.musinsa.com/{len(self.calls)}",
                        "content": f"{query} 내용",
                        "score": 0.9,
                    }
                ]
            },
        )


def make_client(transport, **kwargs):
    defaults = dict(
        cache=TTLLRUCache(max_size=16, ttl=60),
        bucket=TokenBucket(rate=1000, capacity=1000),
        breaker=CircuitBreaker(failure_threshold=3, recovery_timeout=30),
        retry_base_delay=0.0,  # 테스트에서 실제 대기 없음
        retry_max_delay=0.0,
    )
    defaults.update(kwargs)
    return TavilySearchClient(transport=transport, **defaults)


def test_검색_결과_파싱():
    client = make_client(FakeTransport())
    results = client.search("나이키")
    assert len(results) == 1
    assert results[0].title == "나이키 결과"
    assert results[0].is_musinsa is True


def test_캐시_적중시_원격_호출_생략():
    transport = FakeTransport()
    client = make_client(transport)

    client.search("나이키")
    client.search("나이키")

    assert len(transport.calls) == 1  # 두 번째는 캐시


def test_일시적_실패는_재시도로_복구():
    transport = FakeTransport(fail_times=2)
    client = make_client(transport)

    results = client.search("나이키")
    assert len(results) == 1
    assert len(transport.calls) == 3  # 실패 2회 + 성공 1회


def test_서킷_OPEN시_SearchUnavailableError():
    transport = FakeTransport(fail_times=100)
    client = make_client(
        transport,
        breaker=CircuitBreaker(failure_threshold=2, recovery_timeout=30),
        retry_max_attempts=5,
    )

    # 첫 호출: 실패 2회 만에 서킷 OPEN → 재시도 중단 → SearchUnavailableError
    with pytest.raises(SearchUnavailableError):
        client.search("나이키")

    # 이후 호출도 원격 호출 없이 즉시 차단
    calls_before = len(transport.calls)
    with pytest.raises(SearchUnavailableError):
        client.search("아디다스")
    assert len(transport.calls) == calls_before


def test_search_many_병렬_수집():
    transport = FakeTransport()
    client = make_client(transport)

    results = client.search_many(["나이키", "아디다스", "나이키"])  # 중복 포함

    assert set(results.keys()) == {"나이키", "아디다스"}  # 중복 제거
    assert all(len(v) == 1 for v in results.values())


def test_search_flat_URL_중복_제거():
    transport = FakeTransport(
        responses={
            "q1": {"results": [{"title": "A", "url": "https://m.com/1", "content": "a"}]},
            "q2": {"results": [{"title": "B", "url": "https://m.com/1", "content": "b"}]},
        }
    )
    client = make_client(transport)

    flat = client.search_flat(["q1", "q2"])
    assert len(flat) == 1  # 같은 URL은 한 번만


def test_stats_노출():
    client = make_client(FakeTransport())
    client.search("나이키")
    stats = client.stats()

    assert stats["remote_calls"] == 1
    assert stats["circuit_breaker"]["state"] == "closed"
    assert "cache" in stats


def test_API키_없이_transport도_없으면_에러():
    with pytest.raises(ValueError, match="TAVILY_API_KEY"):
        TavilySearchClient(api_key=None)
