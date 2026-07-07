"""에이전트 기능 라우트: 비교 / 추천 / 리뷰 요약.

핸들러가 동기 함수(def)인 이유: 내부의 검색 클라이언트가 블로킹 I/O 이므로,
FastAPI 가 핸들러를 스레드풀에서 실행하게 해 이벤트 루프 블로킹을 피한다.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import ServiceContainer, get_container
from app.api.schemas import (
    CompareRequest,
    CompareResponse,
    RecommendRequest,
    RecommendResponse,
    ReviewSummaryRequest,
    ReviewSummaryResponse,
)
from app.services.render import (
    render_comparison,
    render_recommendation,
    render_review_summary,
)

router = APIRouter(prefix="/api/v1", tags=["agents"])


@router.post(
    "/compare",
    response_model=CompareResponse,
    summary="제품 가격·평점 비교 분석",
    description="2개 이상의 제품을 검색해 가격/평점/스펙을 수집하고 가성비 순으로 비교합니다.",
)
def compare(
    body: CompareRequest,
    container: ServiceContainer = Depends(get_container),
) -> CompareResponse:
    report = container.comparison.compare(body.query)
    return CompareResponse(
        query=report.query,
        winner=report.winner,
        winner_reason=report.winner_reason,
        products=[p.to_dict() for p in report.products],
        markdown=render_comparison(report),
    )


@router.post(
    "/recommendations",
    response_model=RecommendResponse,
    summary="취향 기반 제품 추천",
    description="자유 형식 취향 키워드를 파싱해 BM25 관련도 랭킹으로 제품을 추천합니다.",
)
def recommend(
    body: RecommendRequest,
    container: ServiceContainer = Depends(get_container),
) -> RecommendResponse:
    result = container.recommendation.recommend(body.preference, top_k=body.top_k)
    return RecommendResponse(
        profile=result.profile.to_dict(),
        products=[p.to_dict() for p in result.products],
        markdown=render_recommendation(result),
    )


@router.post(
    "/reviews/summary",
    response_model=ReviewSummaryResponse,
    summary="리뷰 장단점 요약",
    description="무신사 리뷰를 수집해 감성·주제 분석 후 장단점을 요약합니다.",
)
def review_summary(
    body: ReviewSummaryRequest,
    container: ServiceContainer = Depends(get_container),
) -> ReviewSummaryResponse:
    summary = container.review_summary.summarize(body.product_name)
    return ReviewSummaryResponse(
        product_name=summary.product_name,
        source_count=summary.source_count,
        pros=[o.to_dict() for o in summary.pros],
        cons=[o.to_dict() for o in summary.cons],
        markdown=render_review_summary(summary),
    )
