"""Tavily 검색 클라이언트.

인프라 부품들을 계층적으로 조합해 외부 검색 API 호출을 안정화한다::

    search(query)
      └─ ① TTL-LRU 캐시 조회 ── 적중 시 즉시 반환 (API 호출·과금 없음)
      └─ ② 재시도 루프 (지수 백오프 + full jitter)
           └─ ③ 토큰 버킷 ── 호출 속도 제한
           └─ ④ 서킷 브레이커 ── 연속 실패 시 빠른 차단
                └─ ⑤ Tavily API 원격 호출

조합 순서의 근거
----------------
- 캐시가 가장 바깥: 적중하면 rate limit 토큰도 소비하지 않는다.
- 서킷 브레이커가 원격 호출 바로 앞: 실패 기록이 실제 원격 실패만 반영한다.
  (rate limit 대기 초과 같은 클라이언트 사정은 실패로 세지 않음)
- CircuitOpenError 는 재시도 대상에서 제외: 서버가 죽었다는 판정이므로
  백오프 재시도는 무의미하며, 즉시 SearchUnavailableError 로 승격시켜
  API 계층이 503 으로 응답할 수 있게 한다.

병렬 검색
---------
에이전트 하나가 검색어 4~8개를 던지므로, 순차 호출하면 지연이 검색어 수에
비례해 커진다. 검색은 I/O 바운드 작업이라 GIL 의 제약을 받지 않으므로
ThreadPoolExecutor 로 병렬화한다 (지연 ≈ 가장 느린 쿼리 1개 수준).
"""

from __future__ import annotations

import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Iterable, Protocol

from app.infra.cache import TTLLRUCache
from app.infra.circuit_breaker import CircuitBreaker, CircuitOpenError
from app.infra.rate_limiter import TokenBucket
from app.infra.retry import retry

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SearchResult:
    """검색 결과 1건. 외부 API 응답 형식과 도메인 코드를 분리하는 경계 타입."""

    title: str
    url: str
    content: str
    score: float = 0.0

    @property
    def is_musinsa(self) -> bool:
        return "musinsa.com" in self.url.lower()


class SearchError(Exception):
    """검색 호출 실패 (재시도 후에도 실패)."""


class SearchUnavailableError(SearchError):
    """검색 백엔드가 사용 불가 상태 (서킷 OPEN). API 계층에서 503 으로 매핑."""

    def __init__(self, message: str, retry_after: float = 0.0):
        self.retry_after = retry_after
        super().__init__(message)


class SearchClient(Protocol):
    """서비스 계층이 의존하는 검색 인터페이스.

    구현체를 프로토콜 뒤로 숨겨서 테스트 시 가짜 클라이언트를 주입한다
    (의존성 역전 — 서비스는 Tavily 의 존재를 모른다).
    """

    def search(self, query: str, max_results: int | None = None) -> list[SearchResult]:
        ...

    def search_many(
        self, queries: Iterable[str], max_results: int | None = None
    ) -> dict[str, list[SearchResult]]:
        ...


class _RawTransport(Protocol):
    """Tavily SDK 와 동일한 시그니처의 저수준 전송 계층 (테스트 주입용)."""

    def search(self, query: str, search_depth: str, max_results: int) -> dict[str, Any]:
        ...


@dataclass
class _ClientStats:
    remote_calls: int = 0
    failures: int = 0
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def record(self, ok: bool) -> None:
        with self._lock:
            self.remote_calls += 1
            if not ok:
                self.failures += 1


class TavilySearchClient:
    """캐시·속도제한·서킷브레이커·재시도를 갖춘 Tavily 검색 클라이언트."""

    def __init__(
        self,
        api_key: str | None = None,
        *,
        cache: TTLLRUCache | None = None,
        bucket: TokenBucket | None = None,
        breaker: CircuitBreaker | None = None,
        transport: _RawTransport | None = None,
        search_depth: str = "advanced",
        default_max_results: int = 5,
        max_workers: int = 4,
        retry_max_attempts: int = 3,
        retry_base_delay: float = 0.5,
        retry_max_delay: float = 8.0,
        rate_wait_timeout: float = 10.0,
    ):
        if transport is not None:
            self._transport = transport
        else:
            if not api_key:
                raise ValueError(
                    "Tavily API 키가 필요합니다. .env 파일에 TAVILY_API_KEY를 설정하세요."
                )
            from tavily import TavilyClient

            self._transport = TavilyClient(api_key=api_key)

        self._cache = cache or TTLLRUCache(max_size=256, ttl=300.0)
        self._bucket = bucket or TokenBucket(rate=5.0, capacity=10)
        self._breaker = breaker or CircuitBreaker(
            failure_threshold=5, recovery_timeout=30.0
        )
        self._search_depth = search_depth
        self._default_max_results = default_max_results
        self._max_workers = max_workers
        self._rate_wait_timeout = rate_wait_timeout
        self._stats = _ClientStats()

        # 재시도 정책을 인스턴스 설정으로 구성 (SearchError만 재시도)
        self._attempt_with_retry = retry(
            max_attempts=retry_max_attempts,
            base_delay=retry_base_delay,
            max_delay=retry_max_delay,
            retryable=(SearchError,),
            non_retryable=(CircuitOpenError,),
        )(self._search_attempt)

    # --- 내부 호출 경로 ---

    def _raw_search(self, query: str, max_results: int) -> dict[str, Any]:
        try:
            response = self._transport.search(
                query=query,
                search_depth=self._search_depth,
                max_results=max_results,
            )
            self._stats.record(ok=True)
            return response
        except Exception:
            self._stats.record(ok=False)
            raise

    def _search_attempt(self, query: str, max_results: int) -> dict[str, Any]:
        """재시도 1회분: 토큰 확보 → 서킷 브레이커 보호 하에 원격 호출."""
        if not self._bucket.acquire(timeout=self._rate_wait_timeout):
            raise SearchError("검색 호출 대기 시간 초과 (rate limit). 잠시 후 다시 시도하세요.")
        try:
            return self._breaker.call(self._raw_search, query, max_results)
        except (CircuitOpenError, SearchError):
            raise
        except Exception as exc:
            raise SearchError(f"검색 API 호출 실패: {exc}") from exc

    @staticmethod
    def _parse(response: dict[str, Any]) -> list[SearchResult]:
        results = []
        for item in response.get("results") or []:
            url = item.get("url") or ""
            content = item.get("content") or ""
            if not url and not content:
                continue
            results.append(
                SearchResult(
                    title=item.get("title") or "",
                    url=url,
                    content=content,
                    score=float(item.get("score") or 0.0),
                )
            )
        return results

    # --- 공개 API ---

    def search(self, query: str, max_results: int | None = None) -> list[SearchResult]:
        """단일 쿼리 검색. 캐시 적중 시 원격 호출 없이 반환."""
        max_results = max_results or self._default_max_results
        key = (query, max_results, self._search_depth)

        cached = self._cache.get(key)
        if cached is not None:
            return cached

        try:
            response = self._attempt_with_retry(query, max_results)
        except CircuitOpenError as exc:
            raise SearchUnavailableError(str(exc), retry_after=exc.retry_after) from exc

        results = self._parse(response)
        self._cache.put(key, results)
        return results

    def search_many(
        self, queries: Iterable[str], max_results: int | None = None
    ) -> dict[str, list[SearchResult]]:
        """여러 쿼리를 병렬 검색한다.

        일부 쿼리가 실패해도 성공한 결과는 반환한다(부분 성공 허용).
        전부 실패했고 그 원인에 서킷 차단이 포함되면 SearchUnavailableError 를 던져
        호출자가 '백엔드 다운'을 구분할 수 있게 한다.
        """
        unique_queries = list(dict.fromkeys(queries))  # 순서 보존 중복 제거
        if not unique_queries:
            return {}

        results: dict[str, list[SearchResult]] = {}
        unavailable: SearchUnavailableError | None = None

        with ThreadPoolExecutor(
            max_workers=min(self._max_workers, len(unique_queries))
        ) as executor:
            futures = {
                executor.submit(self.search, q, max_results): q for q in unique_queries
            }
            for future, query in futures.items():
                try:
                    results[query] = future.result()
                except SearchUnavailableError as exc:
                    logger.warning("검색 백엔드 사용 불가 (%s)", query)
                    unavailable = exc
                except SearchError as exc:
                    logger.warning("검색 실패 (%s): %s", query, exc)

        if not results and unavailable is not None:
            raise unavailable
        return results

    def search_flat(
        self, queries: Iterable[str], max_results: int | None = None
    ) -> list[SearchResult]:
        """여러 쿼리의 결과를 URL 기준으로 중복 제거해 평탄화한다."""
        merged: dict[str, SearchResult] = {}
        for query_results in self.search_many(queries, max_results).values():
            for result in query_results:
                merged.setdefault(result.url, result)
        return list(merged.values())

    def stats(self) -> dict[str, Any]:
        """관측용 통계 (모니터링 엔드포인트에서 노출)."""
        return {
            "cache": self._cache.stats.to_dict(),
            "cache_size": len(self._cache),
            "circuit_breaker": self._breaker.snapshot(),
            "rate_limiter_tokens": round(self._bucket.available_tokens, 2),
            "remote_calls": self._stats.remote_calls,
            "remote_failures": self._stats.failures,
        }
