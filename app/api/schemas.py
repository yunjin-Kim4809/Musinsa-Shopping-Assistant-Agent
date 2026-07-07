"""API 요청/응답 스키마 (pydantic).

도메인 모델과 분리해 API 계약을 독립적으로 버저닝할 수 있게 한다.
도메인 dataclass → 스키마 변환은 to_dict() + model_validate 로 수행한다.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

# --- 공통 ---


class ErrorResponse(BaseModel):
    error: str = Field(description="오류 유형")
    detail: str = Field(description="사람이 읽을 수 있는 설명")


class HealthResponse(BaseModel):
    status: str = "ok"
    version: str


# --- 비교 분석 ---


class CompareRequest(BaseModel):
    query: str = Field(
        min_length=1,
        max_length=300,
        description="비교 질의. 'vs', '와/과', 쉼표로 제품을 구분",
        examples=["나이키 에어포스 1 vs 아디다스 삼바", "A 코트와 B 코트"],
    )


class PriceInfoSchema(BaseModel):
    current: int | None = None
    original: int | None = None
    discount_rate: float | None = None
    shipping_cost: int | None = None


class RatingInfoSchema(BaseModel):
    rating: float | None = None
    review_count: int | None = None


class ProductSnapshotSchema(BaseModel):
    name: str
    price: PriceInfoSchema
    rating: RatingInfoSchema
    specs: str
    value_score: float
    source_urls: list[str]


class CompareResponse(BaseModel):
    query: str
    winner: str
    winner_reason: str
    products: list[ProductSnapshotSchema]
    markdown: str = Field(description="렌더링된 마크다운 리포트")


# --- 취향 추천 ---


class RecommendRequest(BaseModel):
    preference: str = Field(
        min_length=1,
        max_length=300,
        description="자유 형식 취향 키워드",
        examples=["미니멀리즘, 30만원대, 아르켓 느낌", "스트릿 후드 10만원 이하"],
    )
    top_k: int = Field(default=3, ge=1, le=10, description="추천 제품 수")


class PreferenceProfileSchema(BaseModel):
    raw_input: str
    styles: list[str]
    brands: list[str]
    categories: list[str]
    feels: list[str]
    keywords: list[str]
    budget_label: str | None = None
    budget_min: int | None = None
    budget_max: int | None = None


class RecommendedProductSchema(BaseModel):
    name: str
    url: str
    price: int | None = None
    discount_rate: float | None = None
    is_musinsa: bool
    score: float
    reason: str
    snippet: str


class RecommendResponse(BaseModel):
    profile: PreferenceProfileSchema
    products: list[RecommendedProductSchema]
    markdown: str


# --- 리뷰 요약 ---


class ReviewSummaryRequest(BaseModel):
    product_name: str = Field(
        min_length=1,
        max_length=100,
        description="분석할 제품명",
        examples=["나이키 에어맥스"],
    )


class OpinionSchema(BaseModel):
    topic: str
    sentence: str
    polarity: int = Field(description="+1 긍정 / -1 부정")
    strength: int


class ReviewSummaryResponse(BaseModel):
    product_name: str
    source_count: int
    pros: list[OpinionSchema]
    cons: list[OpinionSchema]
    markdown: str


# --- 운영 관측 ---


class StatsResponse(BaseModel):
    search: dict[str, Any] = Field(description="검색 클라이언트 통계 (캐시/서킷/호출 수)")
