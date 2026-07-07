"""도메인 결과 → 마크다운 렌더러.

표현(프레젠테이션) 로직을 서비스에서 분리해 CLI/API 가 공용으로 쓴다.
"""

from __future__ import annotations

from app.domain.models import (
    ComparisonReport,
    PriceInfo,
    RatingInfo,
    RecommendationResult,
    ReviewSummary,
)


def _format_price(price: PriceInfo) -> str:
    if price.current is None:
        return "정보 없음"
    text = f"{price.current:,}원"
    if price.discount_rate:
        text += f" (할인 {price.discount_rate:.0f}%)"
    if price.shipping_cost == 0:
        text += " · 무료배송"
    return text


def _format_rating(rating: RatingInfo) -> str:
    if rating.rating is None:
        return "정보 없음"
    text = f"{rating.rating:.1f} / 5점"
    if rating.review_count:
        text += f" (리뷰 {rating.review_count:,}개)"
    return text


def _truncate(text: str, limit: int = 80) -> str:
    return text[:limit] + "..." if len(text) > limit else text


def render_comparison(report: ComparisonReport) -> str:
    """비교 결과를 제품 수에 맞춰 마크다운 테이블로 렌더링한다."""
    names = [p.name for p in report.products]
    header = "| 항목 | " + " | ".join(names) + " |"
    divider = "| :--- |" + " :--- |" * len(names)

    def row(label: str, values: list[str]) -> str:
        return f"| **{label}** | " + " | ".join(values) + " |"

    lines = [
        f"### 🛍️ {' vs '.join(names)} 비교 분석",
        "",
        header,
        divider,
        row("현재 가격", [_format_price(p.price) for p in report.products]),
        row("평점", [_format_rating(p.rating) for p in report.products]),
        row("핵심 스펙", [_truncate(p.specs) for p in report.products]),
        row("가성비 점수", [f"{p.value_score:.1f}점" for p in report.products]),
        "",
        f"**🏆 최종 추천: {report.winner}** — {report.winner_reason}",
    ]
    return "\n".join(lines)


def render_recommendation(result: RecommendationResult) -> str:
    """추천 결과를 마크다운으로 렌더링한다."""
    profile = result.profile
    summary_parts = (
        profile.styles + profile.categories + profile.brands + profile.feels
    )
    if profile.budget_label:
        summary_parts.append(profile.budget_label)
    summary = ", ".join(summary_parts) if summary_parts else profile.raw_input

    if not result.products:
        return f"⚠️ '{summary}' 조건에 맞는 제품을 찾지 못했습니다. 키워드를 바꿔 다시 시도해 보세요."

    lines = [f"### ✨ [{summary}] 맞춤 추천 제품 {len(result.products)}가지", ""]
    for idx, product in enumerate(result.products, start=1):
        price_text = f"{product.price:,}원" if product.price else "가격 정보 없음"
        if product.discount_rate:
            price_text += f" (할인 {product.discount_rate:.0f}%)"
        badge = " `무신사`" if product.is_musinsa else ""

        lines.append(f"{idx}. **{product.name}**{badge} — {price_text}")
        lines.append(f"   - 추천 이유: {product.reason}")
        lines.append(f"   - 관련도 점수: {product.score:.1f}점")
        if product.url:
            lines.append(f"   - 링크: {product.url}")
        lines.append("")
    return "\n".join(lines)


def render_review_summary(summary: ReviewSummary) -> str:
    """리뷰 장단점 요약을 마크다운으로 렌더링한다."""
    if summary.source_count == 0:
        return f"⚠️ '{summary.product_name}'에 대한 무신사 리뷰를 찾을 수 없습니다."

    lines = [
        f"### ✅ {summary.product_name} 리뷰 기반 장단점 요약",
        f"*무신사 리뷰 문서 {summary.source_count}건 분석*",
        "",
        "#### 👍 주요 장점",
        "",
    ]
    if summary.pros:
        lines += [f"- **[{o.topic}]** {o.sentence}" for o in summary.pros]
    else:
        lines.append("- 리뷰에서 뚜렷한 장점 의견을 찾지 못했습니다.")

    lines += ["", "#### 👎 유의할 점", ""]
    if summary.cons:
        lines += [f"- **[{o.topic}]** {o.sentence}" for o in summary.cons]
    else:
        lines.append("- 리뷰에서 뚜렷한 단점 의견을 찾지 못했습니다.")

    return "\n".join(lines)
