"""토크나이저 테스트."""

from app.analysis.tokenizer import tokenize


def test_한글_run과_bigram():
    tokens = tokenize("미니멀리즘")
    assert "미니멀리즘" in tokens
    assert "미니" in tokens
    assert "니멀" in tokens
    assert "리즘" in tokens


def test_짧은_한글은_bigram_생략():
    # 2글자 run은 자기 자신이 곧 bigram
    assert tokenize("코트") == ["코트"]


def test_영문은_소문자화():
    assert tokenize("Nike Air") == ["nike", "air"]


def test_혼합_텍스트():
    tokens = tokenize("나이키 Air Force 1 화이트")
    assert "나이키" in tokens
    assert "air" in tokens
    assert "1" in tokens
    assert "화이트" in tokens


def test_구두점_무시():
    tokens = tokenize("가격: 89,000원!")
    assert "가격" in tokens
    assert "89" in tokens


def test_bigram_비활성화():
    tokens = tokenize("미니멀리즘", bigrams=False)
    assert tokens == ["미니멀리즘"]


def test_빈_문자열():
    assert tokenize("") == []


def test_부분_일치_시나리오():
    # 쿼리 "미니멀"과 문서 "미니멀리즘"이 bigram으로 겹치는지
    query = set(tokenize("미니멀"))
    doc = set(tokenize("미니멀리즘"))
    assert query & doc  # 공통 토큰 존재
