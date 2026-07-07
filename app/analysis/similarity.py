"""Levenshtein 편집 거리 기반 문자열 유사도.

여러 검색어로 수집한 제품 후보에는 같은 상품이 조금씩 다른 표기로 섞여 온다.
(예: "나이키 에어포스 1 '07"  vs  "나이키 에어포스1 07 화이트")
URL 중복 제거만으로는 못 잡는 이런 준중복(near-duplicate)을 편집 거리로 걸러낸다.

구현 포인트
-----------
- 동적 계획법 2행 롤링: O(m·n) 시간, O(min(m,n)) 공간.
- 임계값 조기 종료: 중복 판정에는 "거리가 k 이하인가"만 필요하므로,
  DP 행의 최솟값이 k 를 넘는 순간 계산을 중단한다 (그 이후 행은 단조 비감소).
  또한 |len(a) - len(b)| > k 이면 DP 없이 즉시 거절한다 (거리 하한).
"""

from __future__ import annotations

import re

_WHITESPACE_RE = re.compile(r"\s+")


def levenshtein(a: str, b: str, max_distance: int | None = None) -> int:
    """편집 거리(삽입/삭제/치환 각 비용 1).

    max_distance 지정 시, 거리가 이를 초과하면 정확한 값 대신
    max_distance + 1 을 즉시 반환한다 (조기 종료 최적화).
    """
    if a == b:
        return 0

    # 짧은 쪽을 열(column)로 → 공간 O(min(m, n))
    if len(a) < len(b):
        a, b = b, a

    # 길이 차이는 편집 거리의 하한
    if max_distance is not None and len(a) - len(b) > max_distance:
        return max_distance + 1

    if not b:
        return len(a)

    previous = list(range(len(b) + 1))
    for i, char_a in enumerate(a, start=1):
        current = [i]
        for j, char_b in enumerate(b, start=1):
            cost = 0 if char_a == char_b else 1
            current.append(
                min(
                    previous[j] + 1,  # 삭제
                    current[j - 1] + 1,  # 삽입
                    previous[j - 1] + cost,  # 치환
                )
            )
        if max_distance is not None and min(current) > max_distance:
            return max_distance + 1
        previous = current

    return previous[-1]


def _normalize(text: str) -> str:
    return _WHITESPACE_RE.sub(" ", text.strip().lower())


def similarity_ratio(a: str, b: str) -> float:
    """0.0(완전 다름) ~ 1.0(동일) 유사도. 1 - 거리/최대길이."""
    a, b = _normalize(a), _normalize(b)
    if not a and not b:
        return 1.0
    longest = max(len(a), len(b))
    return 1.0 - levenshtein(a, b) / longest


def is_near_duplicate(a: str, b: str, threshold: float = 0.85) -> bool:
    """두 문자열이 준중복인지 판정한다.

    threshold 를 허용 편집 거리 k 로 환산해 조기 종료 DP 를 태운다.
    """
    a, b = _normalize(a), _normalize(b)
    if not a or not b:
        return a == b
    longest = max(len(a), len(b))
    max_dist = int(longest * (1.0 - threshold))
    return levenshtein(a, b, max_distance=max_dist) <= max_dist
