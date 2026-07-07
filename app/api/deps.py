"""의존성 조립(composition root).

설정 → 인프라 부품 → 검색 클라이언트 → 서비스 순으로 객체 그래프를 만든다.
테스트에서는 search_client 에 가짜 구현을 주입해 전체 API 를 오프라인 검증한다.
"""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import Request

from app.config import Settings, get_settings
from app.infra.cache import TTLLRUCache
from app.infra.circuit_breaker import CircuitBreaker
from app.infra.rate_limiter import TokenBucket
from app.infra.search_client import SearchClient, TavilySearchClient
from app.services.comparison import ComparisonService
from app.services.reason import build_reason_generator
from app.services.recommendation import RecommendationService
from app.services.review_summary import ReviewSummaryService


@dataclass
class ServiceContainer:
    settings: Settings
    search_client: SearchClient
    comparison: ComparisonService
    recommendation: RecommendationService
    review_summary: ReviewSummaryService


def build_container(
    settings: Settings | None = None,
    search_client: SearchClient | None = None,
) -> ServiceContainer:
    """서비스 컨테이너를 조립한다. TAVILY_API_KEY 가 없으면 ValueError."""
    settings = settings or get_settings()

    if search_client is None:
        search_client = TavilySearchClient(
            api_key=settings.tavily_api_key,
            cache=TTLLRUCache(
                max_size=settings.cache_max_size,
                ttl=settings.cache_ttl_seconds,
            ),
            bucket=TokenBucket(
                rate=settings.rate_limit_per_second,
                capacity=settings.rate_limit_burst,
            ),
            breaker=CircuitBreaker(
                failure_threshold=settings.circuit_failure_threshold,
                recovery_timeout=settings.circuit_recovery_timeout,
            ),
            search_depth=settings.search_depth,
            default_max_results=settings.search_max_results,
            max_workers=settings.search_max_workers,
            retry_max_attempts=settings.retry_max_attempts,
            retry_base_delay=settings.retry_base_delay,
            retry_max_delay=settings.retry_max_delay,
        )

    reason_generator = build_reason_generator(
        settings.openai_api_key, settings.openai_model
    )

    return ServiceContainer(
        settings=settings,
        search_client=search_client,
        comparison=ComparisonService(search_client),
        recommendation=RecommendationService(search_client, reason_generator),
        review_summary=ReviewSummaryService(search_client),
    )


def get_container(request: Request) -> ServiceContainer:
    """라우트 핸들러용 FastAPI 의존성."""
    return request.app.state.container
