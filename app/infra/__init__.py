"""인프라 계층: 외부 API 호출의 안정성을 책임지는 부품들.

- cache: O(1) TTL-LRU 캐시 (해시맵 + 이중 연결 리스트)
- rate_limiter: 토큰 버킷 알고리즘
- circuit_breaker: CLOSED/OPEN/HALF_OPEN 상태 머신
- retry: 지수 백오프 + full jitter 재시도
- search_client: 위 부품들을 조합한 Tavily 검색 클라이언트
"""

from app.infra.cache import CacheStats, TTLLRUCache
from app.infra.circuit_breaker import CircuitBreaker, CircuitOpenError, CircuitState
from app.infra.rate_limiter import TokenBucket
from app.infra.retry import retry
from app.infra.search_client import (
    SearchClient,
    SearchError,
    SearchResult,
    SearchUnavailableError,
    TavilySearchClient,
)

__all__ = [
    "TTLLRUCache",
    "CacheStats",
    "TokenBucket",
    "CircuitBreaker",
    "CircuitState",
    "CircuitOpenError",
    "retry",
    "SearchClient",
    "SearchResult",
    "SearchError",
    "SearchUnavailableError",
    "TavilySearchClient",
]
