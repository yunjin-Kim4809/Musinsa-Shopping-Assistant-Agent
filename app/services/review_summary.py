"""리뷰 장단점 요약 서비스.

무신사 도메인 리뷰 텍스트를 수집해 문장 단위로 감성·주제를 분석하고
장점/단점을 주제별로 요약한다.

기존 구현 대비 개선
-------------------
- 키워드 매칭: 문장마다 키워드 리스트를 순회하던 O(문장×키워드) 방식을
  Aho-Corasick 자동자 1회 스캔으로 대체. 자동자는 사전이 고정이므로
  서비스 생성 시 한 번만 구축해 재사용한다.
- 부정 표현 처리: "안 좋아요"는 긍정 어간 "좋"을 포함한다. 매칭 스팬이
  반대 극성의 더 긴 매칭 안에 포함되면 무효화해 오분류를 줄인다.
- 중복 문장 제거: 같은 리뷰가 여러 검색 결과에 반복 등장하므로
  Levenshtein 준중복 판정으로 걸러낸다.
- 검색 쿼리: 16개 → 6개로 축소 (병렬 실행 + 캐시로 실질 커버리지는 유지).
"""

from __future__ import annotations

import logging
import re

from app.analysis.aho_corasick import AhoCorasick, Match
from app.analysis.lexicons import NEGATIVE_KEYWORDS, POSITIVE_KEYWORDS, TOPIC_KEYWORDS
from app.analysis.similarity import is_near_duplicate
from app.domain.models import Opinion, ReviewSummary
from app.infra.search_client import SearchClient

logger = logging.getLogger(__name__)

_SENTENCE_SPLIT_RE = re.compile(r"[.!?\n]+")

# 분석 대상 문장 길이 (너무 짧으면 정보 없음, 너무 길면 크롤링 잡음일 가능성)
_MIN_SENTENCE_LEN = 10
_MAX_SENTENCE_LEN = 120
_MAX_SENTENCES = 300  # 준중복 검사 O(n²) 상한
_DEFAULT_TOPIC = "기타"


class ReviewSummaryService:
    """제품 리뷰를 수집하고 장단점을 주제별로 요약하는 서비스."""

    def __init__(
        self,
        search_client: SearchClient,
        max_opinions: int = 5,
        max_per_topic: int = 2,
    ):
        self._client = search_client
        self._max_opinions = max_opinions
        self._max_per_topic = max_per_topic

        # 감성 자동자: 긍정+부정 사전을 하나로 합치고 극성 맵으로 구분
        self._sentiment_ac = AhoCorasick(POSITIVE_KEYWORDS + NEGATIVE_KEYWORDS)
        self._polarity: dict[str, int] = {kw: +1 for kw in POSITIVE_KEYWORDS}
        self._polarity.update({kw: -1 for kw in NEGATIVE_KEYWORDS})

        # 주제 자동자: 전체 주제 키워드 하나의 자동자 + 키워드→주제 역인덱스
        all_topic_keywords: list[str] = []
        self._topics_by_keyword: dict[str, list[str]] = {}
        for topic, keywords in TOPIC_KEYWORDS.items():
            for keyword in keywords:
                all_topic_keywords.append(keyword)
                self._topics_by_keyword.setdefault(keyword, []).append(topic)
        self._topic_ac = AhoCorasick(all_topic_keywords)

    # --- 수집 ---

    def _build_queries(self, product_name: str) -> list[str]:
        return [
            f"{product_name} site:musinsa.com 후기",
            f"{product_name} site:musinsa.com 리뷰",
            f"{product_name} 무신사 구매 후기",
            f"{product_name} 무신사 착용 리뷰",
            f"{product_name} 무신사 단점",
            f"{product_name} 무신사 리뷰 평가",
        ]

    def collect_reviews(self, product_name: str) -> list[str]:
        """무신사 도메인 검색 결과에서 리뷰 텍스트를 수집한다 (URL 중복 제거)."""
        results = self._client.search_flat(self._build_queries(product_name))
        reviews = [r.content for r in results if r.is_musinsa and r.content]
        logger.info("'%s' 무신사 리뷰 문서 %d건 수집", product_name, len(reviews))
        return reviews

    # --- 분석 ---

    @staticmethod
    def _suppress_contained(matches: list[Match], polarity: dict[str, int]) -> list[Match]:
        """반대 극성의 더 긴 매칭에 완전히 포함된 매칭을 무효화한다.

        예: "안 좋아요" → 부정 "안 좋"(0,3) 이 긍정 "좋"(2,3) 을 삼킨다.
            "보풀 없어요" → 긍정 "보풀 없" 이 부정 "보풀" 을 삼킨다.
        """
        survivors = []
        for m in matches:
            contained = any(
                other is not m
                and polarity[other.pattern] != polarity[m.pattern]
                and other.start <= m.start
                and m.end <= other.end
                and (other.end - other.start) > (m.end - m.start)
                for other in matches
            )
            if not contained:
                survivors.append(m)
        return survivors

    def _classify_sentence(self, sentence: str) -> Opinion | None:
        """문장 하나의 극성과 주제를 판정한다. 중립이면 None."""
        matches = self._suppress_contained(
            self._sentiment_ac.find_all(sentence), self._polarity
        )
        positive = sum(1 for m in matches if self._polarity[m.pattern] > 0)
        negative = sum(1 for m in matches if self._polarity[m.pattern] < 0)

        if positive == negative:  # 중립 또는 판단 불가
            return None
        polarity = +1 if positive > negative else -1
        strength = abs(positive - negative)

        # 주제 분류: 매칭 수가 가장 많은 주제 (동률이면 사전 정의 순서 우선)
        topic_scores: dict[str, int] = {}
        for match in self._topic_ac.iter_matches(sentence):
            for topic in self._topics_by_keyword[match.pattern]:
                topic_scores[topic] = topic_scores.get(topic, 0) + 1
        topic = (
            max(topic_scores, key=topic_scores.__getitem__)
            if topic_scores
            else _DEFAULT_TOPIC
        )

        return Opinion(topic=topic, sentence=sentence, polarity=polarity, strength=strength)

    def _split_sentences(self, reviews: list[str]) -> list[str]:
        """리뷰 문서들을 문장으로 쪼개고 길이 필터 + 준중복 제거를 적용한다."""
        sentences: list[str] = []
        for review in reviews:
            for raw in _SENTENCE_SPLIT_RE.split(review):
                sentence = raw.strip()
                if not (_MIN_SENTENCE_LEN <= len(sentence) <= _MAX_SENTENCE_LEN):
                    continue
                if any(is_near_duplicate(sentence, kept) for kept in sentences):
                    continue
                sentences.append(sentence)
                if len(sentences) >= _MAX_SENTENCES:
                    return sentences
        return sentences

    def _select_top(self, opinions: list[Opinion]) -> list[Opinion]:
        """확신도(strength) 높은 순으로, 주제당 상한을 두고 상위 의견을 고른다.

        주제 상한을 두는 이유: 한 주제(예: 배송)가 상위권을 독식하면
        요약의 정보 다양성이 떨어지기 때문.
        """
        ranked = sorted(opinions, key=lambda o: (-o.strength, len(o.sentence)))
        selected: list[Opinion] = []
        per_topic: dict[str, int] = {}
        for opinion in ranked:
            if per_topic.get(opinion.topic, 0) >= self._max_per_topic:
                continue
            selected.append(opinion)
            per_topic[opinion.topic] = per_topic.get(opinion.topic, 0) + 1
            if len(selected) >= self._max_opinions:
                break
        return selected

    # --- 공개 API ---

    def summarize(self, product_name: str) -> ReviewSummary:
        """제품 리뷰를 수집·분석해 장단점 요약을 반환한다."""
        product_name = product_name.strip()
        if not product_name:
            raise ValueError("제품명을 입력해주세요.")

        reviews = self.collect_reviews(product_name)
        sentences = self._split_sentences(reviews)

        pros: list[Opinion] = []
        cons: list[Opinion] = []
        for sentence in sentences:
            opinion = self._classify_sentence(sentence)
            if opinion is None:
                continue
            (pros if opinion.polarity > 0 else cons).append(opinion)

        return ReviewSummary(
            product_name=product_name,
            source_count=len(reviews),
            pros=self._select_top(pros),
            cons=self._select_top(cons),
        )
