"""가격·평점 비교 서비스 테스트."""

import pytest

from app.services.comparison import ComparisonService
from tests.conftest import FakeSearchClient, make_result


def make_client_for_two_products():
    return FakeSearchClient(
        by_query={
            "알파 코트": [
                make_result(
                    title="알파 코트",
                    url="https://www.musinsa.com/products/1",
                    content="알파 코트 판매가: 100,000원 평점: 4.8 리뷰 500개 20% 할인 소재: 울 80%",
                )
            ],
            "베타 코트": [
                make_result(
                    title="베타 코트",
                    url="https://www.musinsa.com/products/2",
                    content="베타 코트 판매가: 300,000원 평점: 3.5 리뷰 20개 소재: 폴리 100%",
                )
            ],
        }
    )


def test_두_제품_비교_및_승자_선정():
    service = ComparisonService(make_client_for_two_products())
    report = service.compare("알파 코트 vs 베타 코트")

    assert len(report.products) == 2
    assert report.winner == "알파 코트"  # 더 싸고 평점 높고 할인 중
    assert report.products[0].value_score > report.products[1].value_score
    assert "최저가" in report.winner_reason
    assert "최고 평점" in report.winner_reason


def test_가격_평점_추출():
    service = ComparisonService(make_client_for_two_products())
    report = service.compare("알파 코트와 베타 코트")

    alpha = next(p for p in report.products if p.name == "알파 코트")
    assert alpha.price.current == 100_000
    assert alpha.price.discount_rate == 20.0
    assert alpha.rating.rating == 4.8
    assert alpha.rating.review_count == 500


def test_제품_1개면_에러():
    service = ComparisonService(FakeSearchClient())
    with pytest.raises(ValueError, match="최소 2개"):
        service.compare("나이키 에어포스")


def test_정보_없는_제품도_중간_점수로_비교():
    client = FakeSearchClient(
        by_query={
            "알파": [
                make_result(
                    content="알파 판매가: 50,000원 평점: 4.5",
                    url="https://www.musinsa.com/1",
                )
            ],
            "미지의제품": [],
        }
    )
    service = ComparisonService(client)
    report = service.compare("알파 vs 미지의제품")

    unknown = next(p for p in report.products if p.name == "미지의제품")
    assert unknown.value_score == 50.0  # 25(가격 미상) + 25(평점 미상)
    assert report.winner == "알파"


def test_비교_대상_상한():
    client = FakeSearchClient(fixtures=[make_result()])
    service = ComparisonService(client)
    report = service.compare("a1 코트, a2 코트, a3 코트, a4 코트, a5 코트")

    assert len(report.products) == 4  # _MAX_PRODUCTS


def test_무신사_결과_우선_사용():
    client = FakeSearchClient(
        by_query={
            "감마": [
                make_result(
                    url="https://blog.example.com/1",
                    content="감마 자켓 판매가: 999,000원",  # 외부 (비싼 가격)
                ),
                make_result(
                    url="https://www.musinsa.com/products/3",
                    content="감마 자켓 판매가: 200,000원 평점: 4.0",  # 무신사
                ),
            ],
            "델타": [],
        }
    )
    service = ComparisonService(client)
    report = service.compare("감마 자켓 vs 델타 자켓")

    gamma = next(p for p in report.products if "감마" in p.name)
    assert gamma.price.current == 200_000  # 무신사 가격 우선
