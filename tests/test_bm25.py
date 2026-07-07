"""BM25 랭킹 테스트."""

import pytest

from app.analysis.bm25 import BM25
from app.analysis.tokenizer import tokenize


def test_관련_문서가_더_높은_점수():
    corpus = [
        tokenize("미니멀 스타일 무신사 코트 추천"),
        tokenize("스트릿 패션 후드티 인기"),
        tokenize("오늘의 날씨와 주식 시황"),
    ]
    bm25 = BM25(corpus)
    query = tokenize("미니멀 코트")

    scores = [bm25.score(query, i) for i in range(3)]
    assert scores[0] > scores[1]
    assert scores[0] > scores[2]


def test_희귀_단어가_흔한_단어보다_높은_가중치():
    # '무신사'는 모든 문서에 등장(IDF 낮음), '아르켓'은 한 문서에만 등장(IDF 높음)
    corpus = [
        ["무신사", "아르켓", "코트"],
        ["무신사", "패딩"],
        ["무신사", "셔츠"],
        ["무신사", "바지"],
    ]
    bm25 = BM25(corpus)

    rare_score = bm25.score(["아르켓"], 0)
    common_score = bm25.score(["무신사"], 0)
    assert rare_score > common_score


def test_IDF는_항상_양수():
    # Lucene 변형 IDF: 모든 문서에 등장하는 단어도 음수가 되지 않아야 함
    corpus = [["공통"], ["공통"], ["공통"]]
    bm25 = BM25(corpus)
    assert bm25.score(["공통"], 0) > 0


def test_TF_포화():
    # 같은 단어 반복이 점수를 선형으로 늘리지 않는다
    corpus = [
        ["코트"] + ["패딩"] * 9,   # 코트 1회
        ["코트"] * 10,             # 코트 10회
    ]
    bm25 = BM25(corpus)
    once = bm25.score(["코트"], 0)
    ten_times = bm25.score(["코트"], 1)
    assert ten_times < once * 10  # 10배가 아니라 포화됨
    assert ten_times > once


def test_문서_길이_정규화():
    # 같은 TF라면 짧은 문서가 유리
    corpus = [
        ["코트", "추천"],
        ["코트"] + ["기타"] * 30,
    ]
    bm25 = BM25(corpus)
    assert bm25.score(["코트"], 0) > bm25.score(["코트"], 1)


def test_rank_내림차순_정렬():
    corpus = [
        tokenize("미니멀 코트"),
        tokenize("미니멀 미니멀 코트 코트"),
        tokenize("주식 시황"),
    ]
    bm25 = BM25(corpus)
    ranked = bm25.rank(tokenize("미니멀 코트"))

    scores = [s for _, s in ranked]
    assert scores == sorted(scores, reverse=True)
    assert ranked[-1][0] == 2  # 무관한 문서가 꼴찌


def test_rank_top_k():
    corpus = [["a"], ["a", "a"], ["b"], ["a", "b"]]
    bm25 = BM25(corpus)
    top2 = bm25.rank(["a"], top_k=2)
    assert len(top2) == 2
    full = bm25.rank(["a"])
    assert [i for i, _ in top2] == [i for i, _ in full[:2]]


def test_빈_쿼리와_미등록_단어():
    bm25 = BM25([["코트"]])
    assert bm25.score([], 0) == 0.0
    assert bm25.score(["존재하지않는단어"], 0) == 0.0


def test_빈_코퍼스():
    bm25 = BM25([])
    assert bm25.rank(["아무거나"]) == []
    assert len(bm25) == 0


def test_인덱스_범위_초과():
    bm25 = BM25([["코트"]])
    with pytest.raises(IndexError):
        bm25.score(["코트"], 5)
