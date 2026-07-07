"""추천 이유 생성기 (전략 패턴).

- HeuristicReasonGenerator: 규칙 기반. 외부 의존성 없음 (기본값)
- OpenAIReasonGenerator: LLM 기반. 실패 시 휴리스틱으로 자동 폴백

서비스는 ReasonGenerator 프로토콜에만 의존하므로, OpenAI 키 유무·장애와
무관하게 추천 파이프라인이 항상 동작한다 (graceful degradation).
"""

from __future__ import annotations

import json
import logging
from typing import Protocol

from app.domain.models import PreferenceProfile, RecommendedProduct

logger = logging.getLogger(__name__)


class ReasonGenerator(Protocol):
    def generate(self, product: RecommendedProduct, profile: PreferenceProfile) -> str:
        ...


class HeuristicReasonGenerator:
    """프로필-제품 매칭 규칙으로 추천 이유 문장을 조립한다."""

    def generate(self, product: RecommendedProduct, profile: PreferenceProfile) -> str:
        text = f"{product.name} {product.snippet}".lower()
        reasons: list[str] = []

        matched_styles = [s for s in profile.styles if s.lower() in text]
        if matched_styles:
            reasons.append(f"{', '.join(matched_styles)} 스타일과 잘 맞습니다")

        matched_brands = [b for b in profile.brands if b.lower() in text]
        if matched_brands:
            reasons.append(f"선호 브랜드({', '.join(matched_brands)}) 제품입니다")

        if product.price and profile.budget_label:
            low, high = profile.budget_min, profile.budget_max
            if (low is None or product.price >= low) and (
                high is None or product.price <= high
            ):
                reasons.append(f"예산({profile.budget_label})에 부합합니다")
            elif high is not None and product.price < high:
                reasons.append("예산보다 저렴해 가성비가 좋습니다")

        if product.discount_rate:
            reasons.append(f"현재 {product.discount_rate:.0f}% 할인 중입니다")

        if product.is_musinsa:
            reasons.append("무신사에서 바로 구매할 수 있습니다")

        if not reasons:
            reasons.append("입력하신 취향 키워드와 관련성이 높은 인기 제품입니다")

        return " · ".join(reasons)


_SYSTEM_PROMPT = """당신은 패션 추천 시스템입니다. 사용자의 취향 키워드와 제품 정보를 비교하여 \
관련성 점수를 0-100 사이로 매기고, 추천 이유를 작성하세요.

JSON 형식으로 응답해야 합니다:
{
  "score": 85,
  "reason": "미니멀 스타일과 캠퍼스룩에 적합한 제품입니다."
}"""


class OpenAIReasonGenerator:
    """OpenAI Chat Completions 로 추천 이유를 생성한다. 실패 시 휴리스틱 폴백."""

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4o",
        fallback: ReasonGenerator | None = None,
    ):
        from openai import OpenAI

        self._client = OpenAI(api_key=api_key)
        self._model = model
        self._fallback = fallback or HeuristicReasonGenerator()

    def generate(self, product: RecommendedProduct, profile: PreferenceProfile) -> str:
        try:
            user_prompt = (
                f"사용자 취향 키워드: {', '.join(profile.all_terms()) or profile.raw_input}\n\n"
                f"제품 정보:\n제목: {product.name}\n내용: {product.snippet[:200]}\n\n"
                "위 제품이 사용자 취향과 얼마나 관련이 있는지 0-100 점수로 평가하고, "
                "추천 이유를 한 문장으로 작성하세요. 반드시 JSON 형식으로 응답하세요."
            )
            response = self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.3,
                response_format={"type": "json_object"},
            )
            payload = json.loads(response.choices[0].message.content)
            reason = str(payload.get("reason", "")).strip()
            if reason:
                return reason
        except Exception as exc:  # LLM 실패는 추천 자체를 막지 않는다
            logger.warning("LLM 추천 이유 생성 실패, 휴리스틱 폴백: %s", exc)
        return self._fallback.generate(product, profile)


def build_reason_generator(
    openai_api_key: str | None, model: str = "gpt-4o"
) -> ReasonGenerator:
    """설정에 따라 적절한 생성기를 고른다. 키가 없으면 휴리스틱."""
    if openai_api_key:
        try:
            return OpenAIReasonGenerator(api_key=openai_api_key, model=model)
        except Exception as exc:
            logger.warning("OpenAI 클라이언트 초기화 실패, 휴리스틱 사용: %s", exc)
    return HeuristicReasonGenerator()
