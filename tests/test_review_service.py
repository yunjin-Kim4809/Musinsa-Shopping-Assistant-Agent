"""리뷰 요약 서비스 테스트."""

import pytest

from app.services.review_summary import ReviewSummaryService
from tests.conftest import FakeSearchClient, make_result


def make_service(reviews: list[str]) -> ReviewSummaryService:
    fixtures = [
        make_result(
            title=f"리뷰 {i}",
            url=f"https://www.musinsa.com/review/{i}",
            content=content,
        )
        for i, content in enumerate(reviews)
    ]
    return ReviewSummaryService(FakeSearchClient(fixtures=fixtures))


def test_긍정_부정_의견_분리():
    service = make_service(
        [
            "이 코트 소재가 정말 부드럽고 좋아요. 배송이 너무 느려서 실망했어요.",
        ]
    )
    summary = service.summarize("테스트 코트")

    assert summary.source_count == 1
    assert any("부드럽" in o.sentence for o in summary.pros)
    assert any("느려" in o.sentence or "실망" in o.sentence for o in summary.cons)


def test_주제_분류():
    service = make_service(
        [
            "원단 재질이 부드럽고 만족스러워요. 배송이 지연되어 불편했습니다.",
        ]
    )
    summary = service.summarize("테스트")

    pro_topics = {o.topic for o in summary.pros}
    con_topics = {o.topic for o in summary.cons}
    assert "소재/재질" in pro_topics
    assert "배송/포장" in con_topics


def test_부정_표현이_긍정으로_오분류되지_않음():
    # "안 좋아요"의 "좋"은 부정 스팬에 포함되므로 긍정으로 세지 않아야 함
    service = make_service(["이 제품 품질이 진짜 안 좋아요 여러분들"])
    summary = service.summarize("테스트")

    assert not summary.pros
    assert len(summary.cons) == 1
    assert summary.cons[0].topic == "품질"


def test_무신사_외_도메인은_제외():
    fixtures = [
        make_result(
            url="https://blog.naver.com/review",
            content="이 제품 정말 좋아요 만족합니다",
        ),
    ]
    service = ReviewSummaryService(FakeSearchClient(fixtures=fixtures))
    summary = service.summarize("테스트")

    assert summary.source_count == 0
    assert not summary.pros


def test_중복_문장은_한_번만_반영():
    duplicated = "핏이 딱 맞고 너무 좋아요 만족합니다"
    service = make_service([duplicated + ". " + duplicated + "."])
    summary = service.summarize("테스트")

    assert len(summary.pros) == 1


def test_주제당_의견_상한():
    reviews = [
        "배송이 빨라서 좋아요 만족합니다. "
        "배송이 정말 빠르고 훌륭해요 최고입니다. "
        "배송 포장도 꼼꼼하고 좋았어요 감사합니다. "
        "핏이 딱 맞아서 좋아요 추천합니다."
    ]
    service = make_service(reviews)
    summary = service.summarize("테스트")

    delivery_count = sum(1 for o in summary.pros if o.topic == "배송/포장")
    assert delivery_count <= 2  # max_per_topic 기본값
    assert any(o.topic == "핏/사이즈" for o in summary.pros)


def test_강한_의견이_우선():
    reviews = [
        "그냥 무난하게 좋아요 어쩌구저쩌구. "
        "소재도 좋고 핏도 좋고 마감도 튼튼하고 정말 만족스러워요."
    ]
    service = make_service(reviews)
    summary = service.summarize("테스트")

    assert summary.pros[0].strength >= summary.pros[-1].strength


def test_빈_제품명은_에러():
    service = make_service([])
    with pytest.raises(ValueError):
        service.summarize("   ")


def test_리뷰_없으면_빈_요약():
    service = ReviewSummaryService(FakeSearchClient(fixtures=[]))
    summary = service.summarize("존재하지 않는 제품")

    assert summary.source_count == 0
    assert summary.pros == []
    assert summary.cons == []
