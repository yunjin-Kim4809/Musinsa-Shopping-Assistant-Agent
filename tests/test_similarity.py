"""Levenshtein 편집 거리 및 준중복 판정 테스트."""

from app.analysis.similarity import is_near_duplicate, levenshtein, similarity_ratio


def test_알려진_편집_거리():
    assert levenshtein("", "") == 0
    assert levenshtein("abc", "abc") == 0
    assert levenshtein("abc", "") == 3
    assert levenshtein("", "abc") == 3
    assert levenshtein("kitten", "sitting") == 3
    assert levenshtein("flaw", "lawn") == 2


def test_한글_편집_거리():
    assert levenshtein("나이키", "나이케") == 1
    assert levenshtein("에어포스", "에어 포스") == 1  # 공백 삽입


def test_인자_순서_무관():
    assert levenshtein("short", "muchlongerstring") == levenshtein(
        "muchlongerstring", "short"
    )


def test_조기_종료_거리_초과시_상한_플러스_1():
    # 실제 거리 3, 상한 1 → 2 반환 (정확한 값 계산 생략)
    assert levenshtein("kitten", "sitting", max_distance=1) == 2


def test_조기_종료_길이차_하한():
    # 길이 차이(7)만으로 상한(2) 초과 → DP 없이 즉시 반환
    assert levenshtein("a", "abcdefgh", max_distance=2) == 3


def test_조기_종료가_정확한_값을_해치지_않음():
    # 상한 이내라면 정확한 거리를 반환해야 함
    assert levenshtein("kitten", "sitting", max_distance=5) == 3


def test_유사도_비율():
    assert similarity_ratio("나이키 에어포스", "나이키 에어포스") == 1.0
    assert similarity_ratio("", "") == 1.0
    assert similarity_ratio("abc", "xyz") == 0.0
    assert 0.0 < similarity_ratio("나이키 에어포스 1", "나이키 에어포스 07") < 1.0


def test_준중복_판정():
    assert is_near_duplicate(
        "나이키 에어포스 1 07 화이트",
        "나이키 에어포스 1 '07 화이트",
    )
    assert not is_near_duplicate("나이키 에어포스", "푸마 스웨이드 클래식")


def test_준중복_정규화():
    # 대소문자/공백 차이는 무시
    assert is_near_duplicate("Nike  Air Force", "nike air force")


def test_빈_문자열_준중복():
    assert is_near_duplicate("", "")
    assert not is_near_duplicate("", "나이키")
