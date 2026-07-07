"""퍼즈(property-based) 테스트.

무작위 입력(고정 시드 → 재현 가능)으로 최적화 구현을 순진한 기준 구현과
대조한다. 예제 기반 테스트가 놓치는 경계 조건을 폭넓게 커버한다.
"""

import random

from app.analysis.aho_corasick import AhoCorasick
from app.analysis.similarity import levenshtein
from tests.test_aho_corasick import naive_find_all

SEED = 20260708
ALPHABET = "가나다라마사아 abxyz"  # 좁은 알파벳 → 우연 매칭·반복 패턴 다수 유발


def random_text(rng: random.Random, min_len: int, max_len: int) -> str:
    length = rng.randint(min_len, max_len)
    return "".join(rng.choice(ALPHABET) for _ in range(length))


def test_aho_corasick_무작위_대조():
    rng = random.Random(SEED)
    for _ in range(200):
        patterns = [random_text(rng, 1, 4) for _ in range(rng.randint(1, 12))]
        text = random_text(rng, 0, 80)

        ac = AhoCorasick(patterns)
        got = {(m.pattern, m.start, m.end) for m in ac.find_all(text)}
        expected = naive_find_all(patterns, text)
        assert got == expected, f"불일치: patterns={patterns!r} text={text!r}"


def reference_levenshtein(a: str, b: str) -> int:
    """검증용 기준 구현: 전체 (m+1)×(n+1) 테이블 DP."""
    m, n = len(a), len(b)
    table = [[0] * (n + 1) for _ in range(m + 1)]
    for i in range(m + 1):
        table[i][0] = i
    for j in range(n + 1):
        table[0][j] = j
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            table[i][j] = min(
                table[i - 1][j] + 1,
                table[i][j - 1] + 1,
                table[i - 1][j - 1] + cost,
            )
    return table[m][n]


def test_levenshtein_무작위_대조():
    rng = random.Random(SEED)
    for _ in range(300):
        a = random_text(rng, 0, 20)
        b = random_text(rng, 0, 20)
        assert levenshtein(a, b) == reference_levenshtein(a, b), f"불일치: {a!r} vs {b!r}"


def test_levenshtein_조기_종료_의미론():
    """max_distance 지정 시: 실제 거리 ≤ k 면 정확한 값, 초과면 k+1."""
    rng = random.Random(SEED + 1)
    for _ in range(300):
        a = random_text(rng, 0, 15)
        b = random_text(rng, 0, 15)
        k = rng.randint(0, 6)
        true_distance = reference_levenshtein(a, b)
        got = levenshtein(a, b, max_distance=k)
        if true_distance <= k:
            assert got == true_distance
        else:
            assert got == k + 1


def test_levenshtein_거리_공리():
    """거리 함수의 성질: 비음수, 동일성, 대칭성, 삼각 부등식."""
    rng = random.Random(SEED + 2)
    for _ in range(100):
        a = random_text(rng, 0, 12)
        b = random_text(rng, 0, 12)
        c = random_text(rng, 0, 12)

        assert levenshtein(a, b) >= 0
        assert levenshtein(a, a) == 0
        assert levenshtein(a, b) == levenshtein(b, a)
        assert levenshtein(a, c) <= levenshtein(a, b) + levenshtein(b, c)
