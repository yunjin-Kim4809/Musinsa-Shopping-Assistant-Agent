"""한국어 친화 토크나이저.

형태소 분석기(KoNLPy 등)는 JVM/모델 의존성이 무거워서 배포가 번거롭다.
대신 다음 전략으로 근사한다:

1. 정규식으로 한글/영문/숫자 연속 구간(run)을 잘라낸다.
2. 한글 run 은 통짜 토큰 + 음절 bigram 을 함께 색인한다.
   예: "미니멀리즘" -> ["미니멀리즘", "미니", "니멀", "멀리", "리즘"]

이렇게 하면 "미니멀"로 검색해도 "미니멀리즘" 문서와 bigram("미니", "니멀")이
겹쳐서 부분 일치가 잡힌다. 조사("무신사의" 등)가 붙어도 어간 bigram 은 남는다.
BM25 와 함께 쓰면 흔한 bigram 은 IDF 가 낮아 자동으로 가중치가 죽으므로,
bigram 노이즈가 랭킹을 크게 왜곡하지 않는다.

트레이드오프: 실제 형태소 경계와 무관한 bigram 도 생성되지만(재현율↑ 정밀도↓),
IDF 가중치가 이를 상쇄한다. 색인 크기는 run 길이에 선형.
"""

from __future__ import annotations

import re

_TOKEN_RE = re.compile(r"[가-힣]+|[a-zA-Z]+|\d+")
_HANGUL_RE = re.compile(r"[가-힣]")


def tokenize(text: str, *, bigrams: bool = True) -> list[str]:
    """텍스트를 토큰 리스트로 변환한다.

    Args:
        text: 원본 텍스트.
        bigrams: 한글 run 에 음절 bigram 을 추가할지 여부.
    """
    tokens: list[str] = []
    for match in _TOKEN_RE.finditer(text.lower()):
        run = match.group()
        tokens.append(run)
        if bigrams and len(run) >= 3 and _HANGUL_RE.match(run):
            tokens.extend(run[i : i + 2] for i in range(len(run) - 1))
    return tokens
