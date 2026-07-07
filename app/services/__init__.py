"""서비스 계층: 세 에이전트의 비즈니스 로직.

검색 클라이언트(SearchClient 프로토콜)를 주입받아 동작하므로
Tavily 없이도 가짜 클라이언트로 전체 로직을 테스트할 수 있다.
"""

from app.services.comparison import ComparisonService
from app.services.reason import (
    HeuristicReasonGenerator,
    OpenAIReasonGenerator,
    ReasonGenerator,
    build_reason_generator,
)
from app.services.recommendation import RecommendationService
from app.services.review_summary import ReviewSummaryService

__all__ = [
    "ComparisonService",
    "RecommendationService",
    "ReviewSummaryService",
    "ReasonGenerator",
    "HeuristicReasonGenerator",
    "OpenAIReasonGenerator",
    "build_reason_generator",
]
