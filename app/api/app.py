"""FastAPI 애플리케이션 팩토리.

실행::

    uvicorn "app.api.app:create_app" --factory --reload
    # 또는
    python -m app.api

예외 → HTTP 상태 코드 매핑
--------------------------
- ValueError (입력 문제)            → 400 Bad Request
- SearchUnavailableError (서킷 OPEN) → 503 Service Unavailable (+ Retry-After)
- SearchError (업스트림 실패)        → 502 Bad Gateway
- pydantic 검증 실패                → 422 (FastAPI 기본)
"""

from __future__ import annotations

import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app import __version__
from app.api.deps import ServiceContainer, build_container
from app.api.routes import agents, system
from app.infra.search_client import SearchError, SearchUnavailableError

logger = logging.getLogger(__name__)

_DESCRIPTION = """\
무신사 쇼핑 도움 에이전트 백엔드.

- **/api/v1/compare**: 제품 가격·평점 비교 분석
- **/api/v1/recommendations**: 취향 기반 제품 추천 (BM25 랭킹)
- **/api/v1/reviews/summary**: 리뷰 장단점 요약 (Aho-Corasick 감성 분석)
- **/api/v1/stats**: 캐시/서킷 브레이커 운영 지표
"""


def create_app(container: ServiceContainer | None = None) -> FastAPI:
    """앱 인스턴스를 생성한다. container 주입 시 테스트용 가짜 의존성 사용 가능."""

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if app.state.container is None:
            # 시작 시점에 조립해 설정 오류(API 키 누락 등)를 fail-fast 로 드러낸다
            app.state.container = build_container()
        yield

    app = FastAPI(
        title="무신사 쇼핑 도움 에이전트 API",
        version=__version__,
        description=_DESCRIPTION,
        lifespan=lifespan,
    )
    app.state.container = container

    # --- 미들웨어: 요청 ID + 처리 시간 로깅 ---

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:12]
        started = time.perf_counter()
        response = await call_next(request)
        elapsed_ms = (time.perf_counter() - started) * 1000
        response.headers["X-Request-ID"] = request_id
        logger.info(
            "%s %s -> %d (%.1fms) [%s]",
            request.method,
            request.url.path,
            response.status_code,
            elapsed_ms,
            request_id,
        )
        return response

    # --- 예외 핸들러 ---

    @app.exception_handler(ValueError)
    async def handle_value_error(request: Request, exc: ValueError):
        return JSONResponse(
            status_code=400,
            content={"error": "invalid_input", "detail": str(exc)},
        )

    @app.exception_handler(SearchUnavailableError)
    async def handle_unavailable(request: Request, exc: SearchUnavailableError):
        return JSONResponse(
            status_code=503,
            content={"error": "search_backend_unavailable", "detail": str(exc)},
            headers={"Retry-After": str(max(1, int(exc.retry_after)))},
        )

    @app.exception_handler(SearchError)
    async def handle_search_error(request: Request, exc: SearchError):
        return JSONResponse(
            status_code=502,
            content={"error": "search_backend_error", "detail": str(exc)},
        )

    app.include_router(system.router)
    app.include_router(agents.router)
    return app
