"""Okapi BM25 문서 랭킹.

취향 키워드(쿼리)와 후보 제품 문서의 관련도를 계산하는 IR 표준 모델.
기존 구현의 "키워드 있으면 +N점" 방식과 달리:

- **IDF**: 모든 문서에 나오는 흔한 단어(예: '무신사', '제품')는 변별력이 없으므로
  가중치를 낮추고, 희귀한 단어의 매칭에 높은 점수를 준다.
- **TF 포화**: 같은 단어가 10번 나온 문서가 1번 나온 문서보다 10배 관련있진 않다.
  k1 파라미터로 TF 기여를 점근적으로 포화시킨다.
- **문서 길이 정규화**: 긴 문서는 우연히 단어를 포함할 확률이 높으므로
  b 파라미터로 평균 대비 길이에 따른 패널티를 준다.

IDF 는 Lucene/ATIRE 변형 ``ln(1 + (N - df + 0.5) / (df + 0.5))`` 을 사용한다.
원조 Robertson-Sparck Jones IDF 는 df > N/2 인 흔한 단어에서 음수가 되어
"단어가 있을수록 감점"되는 이상 동작이 있는데, 이 변형은 항상 양수다.

복잡도: 구축 O(전체 토큰 수), 쿼리당 점수 계산 O(쿼리 토큰 수 × 문서 수),
상위 k 추출은 min-heap 으로 O(문서 수 × log k).
"""

from __future__ import annotations

import heapq
import math
from collections import Counter
from collections.abc import Sequence


class BM25:
    """BM25 인덱스. 후보 문서 집합으로 구축해 쿼리마다 재사용한다.

    Args:
        corpus: 토큰화된 문서 리스트.
        k1: TF 포화 파라미터 (보통 1.2~2.0).
        b: 문서 길이 정규화 강도 (0=무시, 1=완전 정규화).
    """

    def __init__(self, corpus: Sequence[Sequence[str]], k1: float = 1.5, b: float = 0.75):
        self._k1 = k1
        self._b = b
        self._corpus_size = len(corpus)
        self._term_freqs: list[Counter[str]] = [Counter(doc) for doc in corpus]
        self._doc_lens = [len(doc) for doc in corpus]
        self._avgdl = (
            sum(self._doc_lens) / self._corpus_size if self._corpus_size else 0.0
        )

        # 문서 빈도(df) → IDF 사전 계산
        df: Counter[str] = Counter()
        for tf in self._term_freqs:
            df.update(tf.keys())
        self._idf = {
            term: math.log(1 + (self._corpus_size - freq + 0.5) / (freq + 0.5))
            for term, freq in df.items()
        }

    def score(self, query: Sequence[str], index: int) -> float:
        """쿼리와 index 번째 문서의 BM25 점수."""
        if not (0 <= index < self._corpus_size):
            raise IndexError(f"문서 인덱스 범위 초과: {index}")

        tf = self._term_freqs[index]
        doc_len = self._doc_lens[index]
        if doc_len == 0 or self._avgdl == 0:
            return 0.0

        length_norm = 1 - self._b + self._b * (doc_len / self._avgdl)
        score = 0.0
        for term in query:
            freq = tf.get(term)
            if not freq:
                continue
            idf = self._idf.get(term, 0.0)
            score += idf * (freq * (self._k1 + 1)) / (freq + self._k1 * length_norm)
        return score

    def rank(self, query: Sequence[str], top_k: int | None = None) -> list[tuple[int, float]]:
        """전체 문서를 점수화해 (문서 인덱스, 점수) 내림차순으로 반환.

        top_k 지정 시 전체 정렬 O(n log n) 대신 힙 기반 O(n log k)로 상위만 뽑는다.
        """
        scored = (
            (i, self.score(query, i)) for i in range(self._corpus_size)
        )
        if top_k is None:
            return sorted(scored, key=lambda x: x[1], reverse=True)
        return heapq.nlargest(top_k, scored, key=lambda x: x[1])

    def __len__(self) -> int:
        return self._corpus_size
