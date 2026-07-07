"""취향 기반 제품 추천 서비스.

파이프라인::

    취향 입력 ─▶ ① 프로필 파싱 ─▶ ② 검색어 생성 ─▶ ③ 병렬 검색·후보 수집
              ─▶ ④ 준중복 제거 ─▶ ⑤ BM25 + 규칙 랭킹 ─▶ ⑥ 추천 이유 생성

기존 구현 대비 개선
-------------------
- 랭킹: "키워드가 있으면 +N점" 가산 방식을 BM25(IDF·TF 포화·길이 정규화)
  기반 관련도 점수 + 소량의 도메인 규칙 가산으로 교체. 흔한 단어의
  우연 매칭이 점수를 부풀리는 문제가 IDF 로 자연히 해소된다.
- 중복 제거: URL 정확 일치에 더해 Levenshtein 준중복 판정으로
  표기만 다른 같은 상품을 걸러낸다.
- 추천 이유: LLM(선택)/휴리스틱 전략 교체 가능, LLM 장애 시 자동 폴백.
"""

from __future__ import annotations

import heapq
import logging
from dataclasses import dataclass

from app.analysis.aho_corasick import AhoCorasick
from app.analysis.bm25 import BM25
from app.analysis.extractors import extract_price_info, parse_budget
from app.analysis.lexicons import BRAND_KEYWORDS, CATEGORY_KEYWORDS, STYLE_KEYWORDS
from app.analysis.similarity import is_near_duplicate
from app.analysis.tokenizer import tokenize
from app.domain.models import (
    PreferenceProfile,
    RecommendationResult,
    RecommendedProduct,
)
from app.infra.search_client import SearchClient, SearchResult
from app.services.reason import HeuristicReasonGenerator, ReasonGenerator

logger = logging.getLogger(__name__)

_MAX_QUERIES = 8
_MIN_TITLE_LEN = 4
_MIN_CONTENT_LEN = 20

# 랭킹 가중치: BM25(관련도)가 주, 규칙(도메인 지식)이 보조
_BM25_WEIGHT = 60.0
_BONUS_MUSINSA = 20.0
_BONUS_BUDGET_FIT = 15.0
_BONUS_BUDGET_NEAR = 7.0
_BONUS_BRAND = 5.0

# 예산 소프트 필터: 명시 예산의 0.7~1.3배까지 허용
_BUDGET_SOFT_LOW, _BUDGET_SOFT_HIGH = 0.7, 1.3


@dataclass
class _Candidate:
    name: str
    url: str
    price: int | None
    discount_rate: float | None
    is_musinsa: bool
    snippet: str
    doc_tokens: list[str]


class RecommendationService:
    """사용자 취향을 파싱해 관련 제품을 검색·랭킹·추천하는 서비스."""

    def __init__(
        self,
        search_client: SearchClient,
        reason_generator: ReasonGenerator | None = None,
        top_k: int = 3,
    ):
        self._client = search_client
        self._reason = reason_generator or HeuristicReasonGenerator()
        self._top_k = top_k

        # 스타일 자동자: 유의어 → 대표 스타일명 매핑
        style_patterns: list[str] = []
        self._style_by_keyword: dict[str, str] = {}
        for style, keywords in STYLE_KEYWORDS.items():
            for keyword in keywords:
                style_patterns.append(keyword)
                self._style_by_keyword.setdefault(keyword, style)
        self._style_ac = AhoCorasick(style_patterns)
        self._brand_ac = AhoCorasick(BRAND_KEYWORDS)
        self._category_ac = AhoCorasick(CATEGORY_KEYWORDS)

    # --- ① 프로필 파싱 ---

    def parse_profile(self, preference_text: str) -> PreferenceProfile:
        """자유 형식 취향 입력을 구조화 프로필로 변환한다."""
        text = preference_text.strip()
        budget_min, budget_max, budget_label = parse_budget(text)

        styles = list(
            dict.fromkeys(
                self._style_by_keyword[m.pattern] for m in self._style_ac.iter_matches(text)
            )
        )
        brands = list(dict.fromkeys(m.pattern for m in self._brand_ac.iter_matches(text)))
        categories = list(
            dict.fromkeys(m.pattern for m in self._category_ac.iter_matches(text))
        )

        # 사전에 안 잡힌 자유 키워드 (쉼표 구분 조각 중 예산 표현 제외)
        captured = set(styles) | set(brands) | set(categories)
        keywords = []
        for part in text.split(","):
            part = part.strip()
            if len(part) < 2:
                continue
            if parse_budget(part)[2] == part.replace(" ", "") or (
                budget_label and budget_label.replace(" ", "") in part.replace(" ", "")
            ):
                continue  # 순수 예산 표현은 키워드가 아님
            if part in captured:
                continue
            keywords.append(part)

        return PreferenceProfile(
            raw_input=text,
            styles=styles,
            brands=brands,
            categories=categories,
            keywords=keywords,
            budget_label=budget_label,
            budget_min=budget_min,
            budget_max=budget_max,
        )

    # --- ② 검색어 생성 ---

    def _build_queries(self, profile: PreferenceProfile) -> list[str]:
        queries: list[str] = []
        categories = profile.categories or [""]

        for style in profile.styles:
            for category in categories:
                queries.append(f"무신사 {style} 스타일 {category} 추천".replace("  ", " "))
        for brand in profile.brands:
            queries.append(f"무신사 {brand} 인기 제품 추천")
        for keyword in profile.keywords[:3]:
            queries.append(f"무신사 {keyword} 제품 추천")
        if profile.budget_label:
            base = profile.styles[0] if profile.styles else (profile.categories[0] if profile.categories else "")
            queries.append(f"무신사 {profile.budget_label} {base} 추천".replace("  ", " "))

        if not queries:
            queries.append(f"무신사 인기 상품 추천 {profile.raw_input}".strip())

        return queries[:_MAX_QUERIES]

    # --- ③ 후보 수집 / ④ 준중복 제거 ---

    def _to_candidate(self, result: SearchResult) -> _Candidate | None:
        title = result.title.strip()
        # 검색 결과 제목의 사이트명 접미사 제거 (예: "상품명 - 무신사 스토어")
        for sep in (" - 무신사", " | 무신사", " - MUSINSA", " | MUSINSA"):
            if sep in title:
                title = title.split(sep)[0].strip()

        if len(title) < _MIN_TITLE_LEN or len(result.content) < _MIN_CONTENT_LEN:
            return None

        price_info = extract_price_info(f"{result.title} {result.content}")
        return _Candidate(
            name=title[:100],
            url=result.url,
            price=price_info.current,
            discount_rate=price_info.discount_rate,
            is_musinsa=result.is_musinsa,
            snippet=result.content[:300],
            doc_tokens=tokenize(f"{title} {result.content}"),
        )

    @staticmethod
    def _dedupe(candidates: list[_Candidate]) -> list[_Candidate]:
        """무신사 제품 우선 정렬 후, 이름 준중복을 제거한다."""
        ordered = sorted(candidates, key=lambda c: not c.is_musinsa)
        unique: list[_Candidate] = []
        for candidate in ordered:
            if any(is_near_duplicate(candidate.name, kept.name) for kept in unique):
                continue
            unique.append(candidate)
        return unique

    # --- ⑤ 랭킹 ---

    def _rank(
        self, candidates: list[_Candidate], profile: PreferenceProfile, top_k: int
    ) -> list[tuple[_Candidate, float]]:
        query_terms = profile.all_terms() or [profile.raw_input]
        query_tokens = tokenize(" ".join(query_terms))

        bm25 = BM25([c.doc_tokens for c in candidates])
        raw_scores = [bm25.score(query_tokens, i) for i in range(len(candidates))]
        max_score = max(raw_scores, default=0.0)

        scored: list[tuple[_Candidate, float]] = []
        for candidate, raw in zip(candidates, raw_scores, strict=True):
            relevance = (raw / max_score) if max_score > 0 else 0.0
            score = relevance * _BM25_WEIGHT
            score += self._rule_bonus(candidate, profile)
            scored.append((candidate, round(score, 2)))

        # 전체 정렬 대신 힙으로 상위 k개만 추출: O(n log k)
        return heapq.nlargest(top_k, scored, key=lambda x: x[1])

    @staticmethod
    def _rule_bonus(candidate: _Candidate, profile: PreferenceProfile) -> float:
        bonus = 0.0
        if candidate.is_musinsa:
            bonus += _BONUS_MUSINSA

        if candidate.price and (profile.budget_min or profile.budget_max):
            low = profile.budget_min or 0
            high = profile.budget_max or float("inf")
            if low <= candidate.price <= high:
                bonus += _BONUS_BUDGET_FIT
            elif low * _BUDGET_SOFT_LOW <= candidate.price <= high * _BUDGET_SOFT_HIGH:
                bonus += _BONUS_BUDGET_NEAR

        name_lower = candidate.name.lower()
        if any(brand.lower() in name_lower for brand in profile.brands):
            bonus += _BONUS_BRAND
        return bonus

    def _budget_filter(
        self, candidates: list[_Candidate], profile: PreferenceProfile, top_k: int
    ) -> list[_Candidate]:
        """명시 예산의 소프트 범위를 크게 벗어난 후보를 제외한다.

        가격 미상 후보는 유지한다(검색 스니펫에 가격이 없을 뿐일 수 있음).
        필터 결과가 top_k 미만이면 필터를 포기하고 원본을 쓴다.
        """
        if not (profile.budget_min or profile.budget_max):
            return candidates
        low = (profile.budget_min or 0) * _BUDGET_SOFT_LOW
        high = (profile.budget_max or float("inf")) * _BUDGET_SOFT_HIGH
        filtered = [c for c in candidates if c.price is None or low <= c.price <= high]
        return filtered if len(filtered) >= top_k else candidates

    # --- ⑥ 공개 API ---

    def recommend(
        self,
        preference_text: str | None = None,
        profile: PreferenceProfile | None = None,
        top_k: int | None = None,
    ) -> RecommendationResult:
        """취향 텍스트(또는 위저드가 만든 프로필)로 제품을 추천한다."""
        if profile is None:
            if not preference_text or not preference_text.strip():
                raise ValueError("취향 키워드를 입력해주세요.")
            profile = self.parse_profile(preference_text)
        top_k = top_k or self._top_k

        queries = self._build_queries(profile)
        logger.info("추천 검색어 %d개: %s", len(queries), queries)

        results = self._client.search_flat(queries)
        candidates = [c for r in results if (c := self._to_candidate(r))]
        candidates = self._dedupe(candidates)
        candidates = self._budget_filter(candidates, profile, top_k)

        if not candidates:
            return RecommendationResult(profile=profile, products=[])

        products: list[RecommendedProduct] = []
        for candidate, score in self._rank(candidates, profile, top_k):
            product = RecommendedProduct(
                name=candidate.name,
                url=candidate.url,
                price=candidate.price,
                discount_rate=candidate.discount_rate,
                is_musinsa=candidate.is_musinsa,
                score=score,
                snippet=candidate.snippet,
            )
            product.reason = self._reason.generate(product, profile)
            products.append(product)

        return RecommendationResult(profile=profile, products=products)
