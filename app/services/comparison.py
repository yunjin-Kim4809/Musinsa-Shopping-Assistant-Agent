"""제품 가격·평점 비교 분석 서비스.

기존 구현 대비 개선
-------------------
- 제품당 검색 쿼리 7개 → 4개로 축소하고 병렬 실행 (지연 ≈ 1쿼리 수준)
- 2개 제품 하드코딩 → N개 제품 비교 지원
- 무신사 결과 우선 사용, 부족하면 일반 결과로 보완 (기존 정책 유지)
- 가성비 점수 산식을 문서화된 함수로 분리
"""

from __future__ import annotations

import logging

from app.analysis.extractors import (
    extract_price_info,
    extract_rating_info,
    extract_specs,
    split_product_names,
)
from app.domain.models import ComparisonReport, PriceInfo, ProductSnapshot, RatingInfo
from app.infra.search_client import SearchClient

logger = logging.getLogger(__name__)

_MAX_PRODUCTS = 4  # 비교 테이블 가독성을 위한 상한


class ComparisonService:
    """여러 제품의 가격·평점·스펙을 수집해 가성비 순으로 비교하는 서비스."""

    def __init__(self, search_client: SearchClient):
        self._client = search_client

    def _build_queries(self, product_name: str) -> list[str]:
        return [
            f"{product_name} 무신사 가격",
            f"{product_name} 무신사 평점 리뷰",
            f"{product_name} site:musinsa.com",
            f"{product_name} 최저가 할인",
        ]

    def _snapshot(self, product_name: str) -> ProductSnapshot:
        """제품 하나의 가격/평점/스펙 스냅샷을 만든다."""
        results = self._client.search_flat(self._build_queries(product_name))

        # 무신사 결과를 앞에 배치 → 추출기가 무신사 정보를 우선 신뢰
        ordered = sorted(results, key=lambda r: not r.is_musinsa)
        musinsa_texts = [r.content for r in ordered if r.is_musinsa]
        all_texts = [r.content for r in ordered]
        primary_text = " ".join(musinsa_texts if musinsa_texts else all_texts)

        price = extract_price_info(primary_text)
        rating = extract_rating_info(primary_text)

        # 무신사 텍스트에서 못 찾은 정보는 전체 텍스트로 보완
        if musinsa_texts and (price.current is None or rating.rating is None):
            fallback_text = " ".join(all_texts)
            if price.current is None:
                price = extract_price_info(fallback_text)
            if rating.rating is None:
                rating = extract_rating_info(fallback_text)

        return ProductSnapshot(
            name=product_name,
            price=price,
            rating=rating,
            specs=extract_specs(all_texts),
            value_score=self._value_score(price, rating),
            source_urls=[r.url for r in ordered[:5]],
        )

    @staticmethod
    def _value_score(price: PriceInfo, rating: RatingInfo) -> float:
        """가성비 점수 (0~110).

        - 가격 점수 (50점 만점): 낮을수록 높다. 10만원당 5점 감점의 선형 척도.
          정보 없으면 중간값 25점 (미상을 벌점 처리하지 않음).
        - 평점 점수 (50점 만점): 5점 만점 평점의 선형 환산. 미상이면 25점.
        - 할인 보너스 (최대 10점): 할인율 × 0.2
        """
        if price.current:
            price_score = max(0.0, 50.0 - (price.current / 10_000) * 0.5)
        else:
            price_score = 25.0

        if rating.rating:
            rating_score = (rating.rating / 5.0) * 50.0
        else:
            rating_score = 25.0

        discount_bonus = min(10.0, (price.discount_rate or 0) * 0.2)
        return round(price_score + rating_score + discount_bonus, 2)

    @staticmethod
    def _winner_reason(winner: ProductSnapshot, others: list[ProductSnapshot]) -> str:
        reasons = [f"가성비 점수 {winner.value_score:.1f}점으로 최고"]

        priced_others = [o.price.current for o in others if o.price.current]
        if winner.price.current and priced_others and winner.price.current < min(priced_others):
            reasons.append("비교 대상 중 최저가")

        rated_others = [o.rating.rating for o in others if o.rating.rating]
        if winner.rating.rating and rated_others and winner.rating.rating > max(rated_others):
            reasons.append("최고 평점")

        if winner.price.discount_rate:
            reasons.append(f"{winner.price.discount_rate:.0f}% 할인 중")

        return ", ".join(reasons)

    def compare(self, product_query: str) -> ComparisonReport:
        """비교 질의(예: "A 코트 vs B 코트")를 분석해 리포트를 반환한다."""
        names = split_product_names(product_query)
        if len(names) < 2:
            raise ValueError(
                "비교할 제품이 최소 2개 필요합니다. "
                "예: '나이키 에어포스 vs 아디다스 삼바' 또는 'A 코트와 B 코트'"
            )
        if len(names) > _MAX_PRODUCTS:
            names = names[:_MAX_PRODUCTS]
            logger.info("비교 대상이 많아 상위 %d개만 분석합니다", _MAX_PRODUCTS)

        snapshots = [self._snapshot(name) for name in names]
        snapshots.sort(key=lambda s: s.value_score, reverse=True)

        winner = snapshots[0]
        return ComparisonReport(
            query=product_query,
            products=snapshots,
            winner=winner.name,
            winner_reason=self._winner_reason(winner, snapshots[1:]),
        )
