"""REST API 통합 테스트 (가짜 검색 클라이언트 주입, 네트워크 없음)."""

import pytest
from fastapi.testclient import TestClient

from app.api.app import create_app
from app.api.deps import ServiceContainer
from app.config import Settings
from app.infra.search_client import SearchUnavailableError
from app.services.comparison import ComparisonService
from app.services.recommendation import RecommendationService
from app.services.review_summary import ReviewSummaryService
from tests.conftest import FakeSearchClient, make_result


def make_test_client(search_client) -> TestClient:
    settings = Settings(tavily_api_key="test-key", openai_api_key=None)
    container = ServiceContainer(
        settings=settings,
        search_client=search_client,
        comparison=ComparisonService(search_client),
        recommendation=RecommendationService(search_client),
        review_summary=ReviewSummaryService(search_client),
    )
    return TestClient(create_app(container))


@pytest.fixture
def client() -> TestClient:
    fake = FakeSearchClient(
        by_query={
            "알파": [
                make_result(
                    title="알파 코트",
                    url="https://www.musinsa.com/products/1",
                    content="알파 코트 판매가: 100,000원 평점: 4.5 리뷰 300개 미니멀 스타일 좋아요 만족",
                )
            ],
            "베타": [
                make_result(
                    title="베타 코트",
                    url="https://www.musinsa.com/products/2",
                    content="베타 코트 판매가: 200,000원 평점: 4.0 리뷰 100개",
                )
            ],
            "미니멀": [
                make_result(
                    title="미니멀 발마칸 코트",
                    url="https://www.musinsa.com/products/3",
                    content="미니멀 스타일 발마칸 코트 판매가: 320,000원 깔끔한 실루엣",
                )
            ],
            "리뷰": [
                make_result(
                    title="리뷰 페이지",
                    url="https://www.musinsa.com/review/1",
                    content="핏이 딱 맞고 좋아요 만족합니다. 배송이 느려서 아쉬워요.",
                )
            ],
            "후기": [
                make_result(
                    title="후기 페이지",
                    url="https://www.musinsa.com/review/2",
                    content="소재가 부드럽고 만족스러워요 추천합니다.",
                )
            ],
        }
    )
    return make_test_client(fake)


def test_헬스체크(client):
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["version"]


def test_비교_엔드포인트(client):
    response = client.post("/api/v1/compare", json={"query": "알파 코트 vs 베타 코트"})
    assert response.status_code == 200

    body = response.json()
    assert body["winner"] == "알파 코트"
    assert len(body["products"]) == 2
    assert body["products"][0]["price"]["current"] == 100_000
    assert "비교 분석" in body["markdown"]


def test_비교_제품_1개는_400(client):
    response = client.post("/api/v1/compare", json={"query": "혼자인 제품"})
    assert response.status_code == 400
    assert response.json()["error"] == "invalid_input"


def test_추천_엔드포인트(client):
    response = client.post(
        "/api/v1/recommendations",
        json={"preference": "미니멀리즘, 30만원대", "top_k": 3},
    )
    assert response.status_code == 200

    body = response.json()
    assert body["profile"]["styles"] == ["미니멀"]
    assert body["profile"]["budget_label"] == "30만원대"
    assert body["products"]
    assert body["products"][0]["reason"]


def test_추천_top_k_검증(client):
    response = client.post(
        "/api/v1/recommendations",
        json={"preference": "미니멀", "top_k": 99},
    )
    assert response.status_code == 422  # pydantic 검증 (le=10)


def test_리뷰_요약_엔드포인트(client):
    response = client.post(
        "/api/v1/reviews/summary", json={"product_name": "아무 코트"}
    )
    assert response.status_code == 200

    body = response.json()
    assert body["source_count"] >= 1
    assert any(o["polarity"] == 1 for o in body["pros"])
    assert any(o["polarity"] == -1 for o in body["cons"])


def test_빈_본문은_422(client):
    response = client.post("/api/v1/compare", json={})
    assert response.status_code == 422


def test_stats_엔드포인트(client):
    response = client.get("/api/v1/stats")
    assert response.status_code == 200
    assert "search" in response.json()


def test_검색_백엔드_다운시_503():
    class DownSearchClient:
        def search(self, query, max_results=None):
            raise SearchUnavailableError("서킷 열림", retry_after=12.0)

        def search_many(self, queries, max_results=None):
            raise SearchUnavailableError("서킷 열림", retry_after=12.0)

        def search_flat(self, queries, max_results=None):
            raise SearchUnavailableError("서킷 열림", retry_after=12.0)

    client = make_test_client(DownSearchClient())
    response = client.post(
        "/api/v1/reviews/summary", json={"product_name": "나이키"}
    )
    assert response.status_code == 503
    assert response.json()["error"] == "search_backend_unavailable"
    assert response.headers["Retry-After"] == "12"


def test_요청_ID_헤더(client):
    response = client.get("/health")
    assert "X-Request-ID" in response.headers

    echoed = client.get("/health", headers={"X-Request-ID": "test-trace-42"})
    assert echoed.headers["X-Request-ID"] == "test-trace-42"
