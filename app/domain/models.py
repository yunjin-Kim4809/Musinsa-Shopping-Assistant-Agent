"""도메인 모델.

서비스 계층의 입출력을 표현하는 순수 데이터 구조.
외부 라이브러리/API 형식에 의존하지 않아 어느 계층에서도 안전하게 import 가능하다.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class PriceInfo:
    """제품 가격 정보."""

    current: int | None = None  # 현재(할인 적용) 가격, 원
    original: int | None = None  # 정가, 원
    discount_rate: float | None = None  # 할인율, %
    shipping_cost: int | None = None  # 배송비, 원 (0 == 무료배송)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class RatingInfo:
    """제품 평점 정보."""

    rating: float | None = None  # 5점 만점
    review_count: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ProductSnapshot:
    """비교 분석용 제품 스냅샷 (검색 결과에서 추출된 정보의 집약)."""

    name: str
    price: PriceInfo = field(default_factory=PriceInfo)
    rating: RatingInfo = field(default_factory=RatingInfo)
    specs: str = ""
    value_score: float = 0.0  # 가성비 점수 (0~110)
    source_urls: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ComparisonReport:
    """가격·평점 비교 분석 결과."""

    query: str
    products: list[ProductSnapshot]  # value_score 내림차순
    winner: str
    winner_reason: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class PreferenceProfile:
    """사용자 취향 입력을 구조화한 프로필."""

    raw_input: str = ""
    styles: list[str] = field(default_factory=list)
    brands: list[str] = field(default_factory=list)
    categories: list[str] = field(default_factory=list)
    feels: list[str] = field(default_factory=list)  # 편안한/따뜻한 등 촉감·느낌
    keywords: list[str] = field(default_factory=list)  # 자유 키워드
    budget_label: str | None = None
    budget_min: int | None = None
    budget_max: int | None = None

    def all_terms(self) -> list[str]:
        """검색·랭킹에 쓸 전체 취향 용어 (중복 제거, 순서 보존)."""
        terms = self.styles + self.brands + self.categories + self.feels + self.keywords
        return list(dict.fromkeys(t for t in terms if t))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class RecommendedProduct:
    """추천 결과 제품 1건."""

    name: str
    url: str = ""
    price: int | None = None
    discount_rate: float | None = None
    is_musinsa: bool = False
    score: float = 0.0  # 최종 랭킹 점수 (BM25 + 규칙 가산)
    reason: str = ""  # 추천 이유
    snippet: str = ""  # 검색 결과 요약문

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class RecommendationResult:
    """취향 기반 추천 결과."""

    profile: PreferenceProfile
    products: list[RecommendedProduct]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Opinion:
    """리뷰에서 추출한 의견 1건."""

    topic: str  # 핏/사이즈, 소재, 배송 등
    sentence: str  # 근거 문장
    polarity: int  # +1 긍정 / -1 부정
    strength: int = 1  # 감성 키워드 매칭 강도 (근거 문장의 확신도)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ReviewSummary:
    """리뷰 장단점 요약 결과."""

    product_name: str
    source_count: int  # 분석에 사용된 리뷰 문서 수
    pros: list[Opinion] = field(default_factory=list)
    cons: list[Opinion] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
