"""공용 테스트 픽스처: 가짜 검색 클라이언트."""

from __future__ import annotations

import pytest

from app.infra.search_client import SearchResult


class FakeSearchClient:
    """SearchClient 프로토콜의 결정적(deterministic) 가짜 구현.

    fixtures 리스트를 받아 모든 쿼리에 같은 결과를 돌려주거나,
    by_query 로 쿼리 부분 문자열 → 결과 매핑을 지정할 수 있다.
    """

    def __init__(
        self,
        fixtures: list[SearchResult] | None = None,
        by_query: dict[str, list[SearchResult]] | None = None,
    ):
        self.fixtures = fixtures or []
        self.by_query = by_query or {}
        self.queries_seen: list[str] = []

    def _lookup(self, query: str) -> list[SearchResult]:
        for fragment, results in self.by_query.items():
            if fragment in query:
                return results
        return self.fixtures

    def search(self, query, max_results=None):
        self.queries_seen.append(query)
        return self._lookup(query)

    def search_many(self, queries, max_results=None):
        return {q: self.search(q) for q in dict.fromkeys(queries)}

    def search_flat(self, queries, max_results=None):
        merged = {}
        for results in self.search_many(queries).values():
            for result in results:
                merged.setdefault(result.url, result)
        return list(merged.values())


def make_result(
    title="상품",
    url="https://www.musinsa.com/products/1",
    content="내용",
    score=0.5,
) -> SearchResult:
    return SearchResult(title=title, url=url, content=content, score=score)


@pytest.fixture
def fake_client():
    return FakeSearchClient()
