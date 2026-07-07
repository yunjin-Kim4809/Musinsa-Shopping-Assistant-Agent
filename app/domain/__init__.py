"""도메인 계층: 외부 의존성이 없는 순수 데이터 모델."""

from app.domain.models import (
    ComparisonReport,
    Opinion,
    PreferenceProfile,
    PriceInfo,
    ProductSnapshot,
    RatingInfo,
    RecommendationResult,
    RecommendedProduct,
    ReviewSummary,
)

__all__ = [
    "PriceInfo",
    "RatingInfo",
    "ProductSnapshot",
    "ComparisonReport",
    "PreferenceProfile",
    "RecommendedProduct",
    "RecommendationResult",
    "Opinion",
    "ReviewSummary",
]
