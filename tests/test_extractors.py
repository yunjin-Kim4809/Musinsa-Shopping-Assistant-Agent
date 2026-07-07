"""정보 추출기 테스트."""

from app.analysis.extractors import (
    extract_price_info,
    extract_rating_info,
    extract_specs,
    parse_budget,
    split_product_names,
)


class TestSplitProductNames:
    def test_와_접속사(self):
        assert split_product_names("나이키 에어포스 화이트와 푸마 스웨이드") == [
            "나이키 에어포스 화이트",
            "푸마 스웨이드",
        ]

    def test_vs_구분자(self):
        assert split_product_names("A 코트 vs B 코트") == ["A 코트", "B 코트"]
        assert split_product_names("A 코트 VS B 코트") == ["A 코트", "B 코트"]

    def test_쉼표_구분자(self):
        assert split_product_names("나이키, 아디다스, 뉴발란스") == [
            "나이키",
            "아디다스",
            "뉴발란스",
        ]

    def test_단어_내부의_와는_보존(self):
        # '스니커즈와이드'의 '와'는 접속사가 아님 (뒤에 공백 없음)
        assert split_product_names("스니커즈와이드 팬츠") == ["스니커즈와이드 팬츠"]

    def test_단일_제품(self):
        assert split_product_names("나이키 에어포스") == ["나이키 에어포스"]


class TestExtractPriceInfo:
    def test_라벨_붙은_가격_우선(self):
        info = extract_price_info("판매가: 89,000원 어쩌구 조회수 129,000")
        assert info.current == 89_000

    def test_정가와_할인율_계산(self):
        info = extract_price_info("정가 100,000원 판매가 80,000원")
        assert info.current == 80_000
        assert info.original == 100_000
        assert info.discount_rate == 20.0

    def test_할인율에서_정가_역산(self):
        info = extract_price_info("가격: 80,000원 20% 할인")
        assert info.current == 80_000
        assert info.discount_rate == 20.0
        assert info.original == 100_000

    def test_라벨_없는_가격은_문맥_필터(self):
        # '리뷰' 근처의 숫자는 가격으로 취급하지 않음
        info = extract_price_info("리뷰 12,000개 돌파! 이 상품 45,000원에 판매중")
        assert info.current == 45_000

    def test_무료배송(self):
        info = extract_price_info("가격 50,000원 무료배송")
        assert info.shipping_cost == 0

    def test_배송비(self):
        info = extract_price_info("가격 50,000원, 배송비 3,000원")
        assert info.shipping_cost == 3_000

    def test_비상식적_가격_무시(self):
        info = extract_price_info("가격: 100원")  # 5천원 미만
        assert info.current is None

    def test_가격_정보_없음(self):
        info = extract_price_info("이 제품 정말 좋아요")
        assert info.current is None
        assert info.discount_rate is None


class TestExtractRatingInfo:
    def test_평점_라벨(self):
        info = extract_rating_info("평점: 4.5 리뷰 1,234개")
        assert info.rating == 4.5
        assert info.review_count == 1_234

    def test_5점_만점_표기(self):
        info = extract_rating_info("이 상품은 4.8/5 를 기록했다")
        assert info.rating == 4.8

    def test_여러_평점은_평균(self):
        info = extract_rating_info("평점 4.0 평점 5.0")
        assert info.rating == 4.5

    def test_범위_밖_평점_무시(self):
        info = extract_rating_info("평점: 9.9")
        assert info.rating is None

    def test_정보_없음(self):
        info = extract_rating_info("좋은 상품입니다")
        assert info.rating is None
        assert info.review_count is None


class TestParseBudget:
    def test_만원대(self):
        assert parse_budget("30만원대 코트") == (300_000, 400_000, "30만원대")

    def test_범위(self):
        assert parse_budget("20~30만원 사이") == (200_000, 300_000, "20~30만원")

    def test_범위_역순_보정(self):
        assert parse_budget("30~20만원") == (200_000, 300_000, "20~30만원")

    def test_이하(self):
        assert parse_budget("10만원 이하로") == (None, 100_000, "10만원 이하")

    def test_이상(self):
        assert parse_budget("50만원 이상") == (500_000, None, "50만원 이상")

    def test_단일_금액(self):
        assert parse_budget("예산 25만원") == (250_000, 250_000, "25만원")

    def test_예산_없음(self):
        assert parse_budget("미니멀 스타일") == (None, None, None)


class TestExtractSpecs:
    def test_스펙_라인_추출(self):
        texts = ["소재: 면 100%\n아무 관련 없는 줄\n사이즈: S, M, L"]
        specs = extract_specs(texts)
        assert "소재: 면 100%" in specs
        assert "사이즈: S, M, L" in specs

    def test_스펙_없으면_본문_요약(self):
        texts = ["이 제품은 아주 훌륭한 제품입니다"]
        assert "훌륭한" in extract_specs(texts)

    def test_빈_입력(self):
        assert extract_specs([]) == "스펙 정보 없음"
