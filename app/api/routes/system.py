"""시스템 라우트: 헬스체크 / 운영 지표."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app import __version__
from app.api.deps import ServiceContainer, get_container
from app.api.schemas import HealthResponse, StatsResponse

router = APIRouter(tags=["system"])


@router.get("/health", response_model=HealthResponse, summary="헬스체크")
def health() -> HealthResponse:
    return HealthResponse(status="ok", version=__version__)


@router.get(
    "/api/v1/stats",
    response_model=StatsResponse,
    summary="운영 지표",
    description="캐시 적중률, 서킷 브레이커 상태, 원격 호출 수 등 검색 클라이언트 통계.",
)
def stats(container: ServiceContainer = Depends(get_container)) -> StatsResponse:
    client = container.search_client
    payload = client.stats() if hasattr(client, "stats") else {}
    return StatsResponse(search=payload)
