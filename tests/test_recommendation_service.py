"""취향 기반 추천 서비스 테스트."""

import pytest

from app.services.recommendation import RecommendationService
from tests.conftest import FakeSearchClient, make_result


def test_프로필_파싱_스타일_예산_브랜드():
    service = RecommendationService(FakeSearchClient())
    profile = service.parse_profile("미니멀리즘, 30만원대, 아르켓 느낌")

    assert "미니멀" in profile.styles
    assert profile.budget_label == "30만원대"
    assert profile.budget_min == 300_000
    assert profile.budget_max == 400_000
    assert "아르켓" in profile.brands


def test_프로필_파싱_카테고리():
    service = RecommendationService(FakeSearchClient())
    profile = service.parse_profile("스트릿 후드 20만원 이하")

    assert "스트릿" in profile.styles
    assert profile.budget_max == 200_000
    assert profile.budget_min is None


def test_취향_관련_제품이_상위_랭킹():
    fixtures = [
        make_result(
            title="미니멀 울 싱글 코트",
            url="https://www.musinsa.com/products/1",
            content="미니멀 심플 디자인 울 코트. 판매가: 320,000원. 깔끔한 모노톤 미니멀리즘",
        ),
        make_result(
            title="그래픽 오버핏 반팔티",
            url="https://www.musinsa.com/products/2",
            content="스트릿 그래픽 프린트 반팔 티셔츠 판매가: 29,000원",
        ),
    ]
    service = RecommendationService(FakeSearchClient(fixtures=fixtures), top_k=2)
    result = service.recommend("미니멀리즘, 30만원대 코트")

    assert result.products[0].name == "미니멀 울 싱글 코트"
    assert result.products[0].score > result.products[1].score


def test_무신사_제품_가산점():
    fixtures = [
        make_result(
            title="미니멀 코트 A",
            url="https://blog.example.com/1",
            content="미니멀 스타일 코트 소개 블로그 글입니다 판매가: 300,000원",
        ),
        make_result(
            title="미니멀 코트 B",
            url="https://www.musinsa.com/products/2",
            content="미니멀 스타일 코트 무신사 단독 판매가: 300,000원",
        ),
    ]
    service = RecommendationService(FakeSearchClient(fixtures=fixtures), top_k=2)
    result = service.recommend("미니멀 코트")

    assert result.products[0].is_musinsa


def test_준중복_제품은_하나만():
    fixtures = [
        make_result(
            title="나이키 에어포스 1 07 화이트",
            url="https://www.musinsa.com/products/1",
            content="나이키 에어포스 스니커즈 화이트 판매가: 139,000원 인기",
        ),
        make_result(
            title="나이키 에어포스 1 '07 화이트",
            url="https://www.musinsa.com/products/2",
            content="나이키 에어포스 스니커즈 클래식 판매가: 139,000원 추천",
        ),
    ]
    service = RecommendationService(FakeSearchClient(fixtures=fixtures), top_k=3)
    result = service.recommend("나이키 스니커즈")

    assert len(result.products) == 1


def test_제목이_너무_짧거나_내용_없는_결과는_제외():
    fixtures = [
        make_result(title="ab", url="https://m.com/1", content="긴 내용 " * 20),
        make_result(title="정상적인 제품명", url="https://m.com/2", content="짧음"),
    ]
    service = RecommendationService(FakeSearchClient(fixtures=fixtures))
    result = service.recommend("아무 취향")

    assert result.products == []


def test_사이트명_접미사_제거():
    fixtures = [
        make_result(
            title="울 발마칸 코트 - 무신사 스토어",
            url="https://www.musinsa.com/products/1",
            content="미니멀 울 발마칸 코트 판매가: 350,000원 " * 3,
        ),
    ]
    service = RecommendationService(FakeSearchClient(fixtures=fixtures))
    result = service.recommend("미니멀 코트")

    assert result.products[0].name == "울 발마칸 코트"


def test_빈_입력은_에러():
    service = RecommendationService(FakeSearchClient())
    with pytest.raises(ValueError):
        service.recommend("  ")


def test_검색_결과_없으면_빈_추천():
    service = RecommendationService(FakeSearchClient(fixtures=[]))
    result = service.recommend("미니멀")

    assert result.products == []
    assert result.profile.styles == ["미니멀"]


def test_추천_이유_생성됨():
    fixtures = [
        make_result(
            title="미니멀 무지 티셔츠",
            url="https://www.musinsa.com/products/1",
            content="미니멀 베이직 무지 티셔츠 판매가: 29,000원 깔끔한 데일리",
        ),
    ]
    service = RecommendationService(FakeSearchClient(fixtures=fixtures))
    result = service.recommend("미니멀")

    assert result.products[0].reason  # 비어있지 않음
    assert "미니멀" in result.products[0].reason or "무신사" in result.products[0].reason
