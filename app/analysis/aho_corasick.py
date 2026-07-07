"""Aho-Corasick 다중 패턴 문자열 매칭 자동자.

리뷰 감성 분석은 문장마다 감성/주제 키워드 수백 개의 등장 여부를 검사한다.
키워드마다 `keyword in sentence` 를 반복하면 O(패턴 수 × 문장 길이) 이지만,
Aho-Corasick 자동자는 전체 패턴을 트라이로 만들고 실패 링크(failure link)를
연결해 **텍스트를 단 한 번 스캔**하면서 모든 패턴의 모든 등장을 찾는다.

복잡도
------
- 구축: O(모든 패턴 길이 합)
- 검색: O(텍스트 길이 + 매칭 수)  — 패턴 수와 무관

구조
----
- goto:   트라이 간선. 노드별 {문자: 다음 노드} 해시맵
- fail:   실패 링크. 현재까지 읽은 접미사 중 트라이에 존재하는 가장 긴 것
          (KMP 실패 함수를 트라이로 일반화한 것. BFS 로 계산 → 부모의 fail 이
          자식보다 먼저 확정되는 위상 순서가 보장된다)
- output: 노드에서 끝나는 패턴 목록. 실패 링크를 따라가면 나오는 짧은 패턴들
          (예: "가성비" 안의 "성비")도 output 병합으로 함께 보고된다.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Iterable, Iterator


@dataclass(frozen=True)
class Match:
    """패턴 매칭 결과. end 는 배타적(파이썬 슬라이스 규약)."""

    pattern: str
    start: int
    end: int


class AhoCorasick:
    """다중 패턴 매칭 자동자. 패턴 집합으로 한 번 구축해 여러 텍스트에 재사용한다."""

    def __init__(self, patterns: Iterable[str]):
        # 순서 보존 중복 제거, 빈 패턴 제외
        unique = list(dict.fromkeys(p for p in patterns if p))
        if not unique:
            raise ValueError("최소 1개 이상의 비어있지 않은 패턴이 필요합니다.")

        self._goto: list[dict[str, int]] = [{}]
        self._fail: list[int] = [0]
        self._output: list[list[str]] = [[]]

        for pattern in unique:
            self._insert(pattern)
        self._build_failure_links()

    def _insert(self, pattern: str) -> None:
        """트라이에 패턴을 삽입한다."""
        node = 0
        for char in pattern:
            nxt = self._goto[node].get(char)
            if nxt is None:
                nxt = len(self._goto)
                self._goto.append({})
                self._fail.append(0)
                self._output.append([])
                self._goto[node][char] = nxt
            node = nxt
        self._output[node].append(pattern)

    def _build_failure_links(self) -> None:
        """BFS 로 실패 링크를 계산한다. 깊이 순 방문이라 부모 fail 이 항상 먼저 확정된다."""
        queue: deque[int] = deque()

        # 깊이 1: 실패하면 루트로
        for child in self._goto[0].values():
            queue.append(child)

        while queue:
            node = queue.popleft()
            for char, child in self._goto[node].items():
                queue.append(child)

                # 부모의 실패 링크에서 시작해 char 간선이 있는 조상을 찾는다
                fallback = self._fail[node]
                while fallback and char not in self._goto[fallback]:
                    fallback = self._fail[fallback]
                self._fail[child] = self._goto[fallback].get(char, 0)
                if self._fail[child] == child:  # 루트 직계가 자기 자신을 가리키는 경우 방지
                    self._fail[child] = 0

                # 실패 링크가 가리키는 노드의 매칭도 함께 보고 (접미사 패턴 병합)
                self._output[child].extend(self._output[self._fail[child]])

    def iter_matches(self, text: str) -> Iterator[Match]:
        """텍스트를 한 번 스캔하며 모든 패턴 매칭을 생성한다."""
        node = 0
        for i, char in enumerate(text):
            while node and char not in self._goto[node]:
                node = self._fail[node]
            node = self._goto[node].get(char, 0)
            for pattern in self._output[node]:
                yield Match(pattern, i - len(pattern) + 1, i + 1)

    def find_all(self, text: str) -> list[Match]:
        return list(self.iter_matches(text))

    def count(self, text: str) -> dict[str, int]:
        """패턴별 등장 횟수."""
        counts: dict[str, int] = {}
        for match in self.iter_matches(text):
            counts[match.pattern] = counts.get(match.pattern, 0) + 1
        return counts

    def contains_any(self, text: str) -> bool:
        return next(self.iter_matches(text), None) is not None
