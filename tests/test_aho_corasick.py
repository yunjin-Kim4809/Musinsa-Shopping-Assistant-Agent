"""Aho-Corasick 자동자 테스트. naive 매칭과 결과를 대조해 정확성을 검증한다."""

import pytest

from app.analysis.aho_corasick import AhoCorasick, Match


def naive_find_all(patterns, text):
    """검증용 기준 구현: 모든 (패턴, 위치) 쌍을 브루트포스로 찾는다."""
    matches = set()
    for pattern in set(patterns):
        start = 0
        while (idx := text.find(pattern, start)) != -1:
            matches.add((pattern, idx, idx + len(pattern)))
            start = idx + 1
    return matches


def test_단일_패턴():
    ac = AhoCorasick(["좋"])
    assert ac.find_all("정말 좋아요 좋습니다") == [
        Match("좋", 3, 4),
        Match("좋", 7, 8),
    ]


def test_겹치는_패턴_모두_보고():
    # "가성비" 안에 "성비"가 포함됨 → 실패 링크의 output 병합으로 둘 다 잡혀야 함
    ac = AhoCorasick(["가성비", "성비"])
    found = {m.pattern for m in ac.find_all("이 옷 가성비 최고")}
    assert found == {"가성비", "성비"}


def test_접두사_관계_패턴():
    ac = AhoCorasick(["편안", "편안하고"])
    found = {(m.pattern, m.start) for m in ac.find_all("아주 편안하고 좋아요")}
    assert ("편안", 3) in found
    assert ("편안하고", 3) in found


def test_naive와_결과_일치():
    patterns = ["좋", "안 좋", "좋지 않", "배송", "빠른 배송", "송", "가격", "격"]
    texts = [
        "배송이 빠른 배송이라 좋았어요 근데 가격이 안 좋네요",
        "좋지 않은 품질, 배송 지연",
        "송장번호 가격격격",
        "",
        "아무 매칭 없는 문장",
    ]
    ac = AhoCorasick(patterns)
    for text in texts:
        got = {(m.pattern, m.start, m.end) for m in ac.find_all(text)}
        assert got == naive_find_all(patterns, text), f"불일치: {text!r}"


def test_count():
    ac = AhoCorasick(["좋", "별로"])
    counts = ac.count("좋아요 좋아요 별로예요")
    assert counts == {"좋": 2, "별로": 1}


def test_contains_any():
    ac = AhoCorasick(["보풀", "이염"])
    assert ac.contains_any("보풀이 생겨요") is True
    assert ac.contains_any("아주 만족합니다") is False


def test_중복_빈_패턴_처리():
    ac = AhoCorasick(["좋", "좋", "", "별로"])
    assert {m.pattern for m in ac.find_all("좋아요 별로")} == {"좋", "별로"}


def test_패턴_없으면_에러():
    with pytest.raises(ValueError):
        AhoCorasick([])
    with pytest.raises(ValueError):
        AhoCorasick(["", ""])


def test_긴_텍스트_선형_스캔():
    ac = AhoCorasick(["나이키", "아디다스"])
    text = "나이키 " * 1000
    assert len(ac.find_all(text)) == 1000
