"""대화형 CLI.

REST API 와 동일한 서비스 계층을 사용하는 터미널 인터페이스.
메뉴 4번(인터랙티브 위저드)은 해커톤 당시 소실된 `취향기반추천.py` 의
UX 를 복원한 것이다 (카테고리→스타일→브랜드→느낌→가격대 5단계 선택).
"""

from __future__ import annotations

import logging
import os
import sys

from dotenv import load_dotenv

from app.api.deps import ServiceContainer, build_container
from app.config import Settings
from app.domain.models import PreferenceProfile
from app.infra.search_client import SearchError, SearchUnavailableError
from app.services.render import (
    render_comparison,
    render_recommendation,
    render_review_summary,
)

BAR = "=" * 60
LINE = "-" * 60

# --- 인터랙티브 위저드 선택지 (소실된 원본 모듈에서 복원) ---

_CATEGORY_OPTIONS = [
    ("1", "상의"), ("2", "하의"), ("3", "바지"), ("4", "아우터"),
    ("5", "신발"), ("6", "악세서리"), ("7", "가방"), ("8", "모자"),
]
_STYLE_OPTIONS = [
    ("1", "미니멀"), ("2", "캠퍼스"), ("3", "스트릿"), ("4", "오피스"),
    ("5", "캐주얼"), ("6", "데이트"), ("7", "댄디"), ("8", "아메카지"),
    ("9", "빈티지"), ("10", "모던"), ("11", "클래식"), ("12", "시크"),
    ("13", "페미닌"), ("14", "유니섹스"),
]
_FEEL_OPTIONS = [
    ("1", "편안한"), ("2", "따뜻한"), ("3", "시원한"),
    ("4", "가벼운"), ("5", "부드러운"),
]
_PRICE_OPTIONS: list[tuple[str, str, tuple[int | None, int | None] | None]] = [
    ("1", "5만원 이하", (None, 50_000)),
    ("2", "5만원 ~ 10만원", (50_000, 100_000)),
    ("3", "10만원 ~ 20만원", (100_000, 200_000)),
    ("4", "20만원 이상", (200_000, None)),
    ("0", "가격 무관", None),
]


def _pick_multi(title: str, options: list[tuple[str, str]], allow_skip: bool = True) -> list[str]:
    """번호 목록에서 복수 선택을 받는다. 0 또는 빈 입력은 건너뛰기."""
    print(f"\n{title}")
    print(LINE)
    for number, label in options:
        print(f"  {number}. {label}")
    if allow_skip:
        print("  0. 건너뛰기")

    raw = input("\n선택 (번호를 쉼표로 구분, 예: 1,3): ").strip()
    if not raw or raw == "0":
        return []

    valid = dict(options)
    picked = []
    for token in raw.split(","):
        token = token.strip()
        if token in valid and valid[token] not in picked:
            picked.append(valid[token])
    return picked


def run_wizard() -> PreferenceProfile:
    """5단계 취향 선택 위저드로 PreferenceProfile 을 만든다."""
    print(f"\n{BAR}\n🎨 취향 선택하기\n{BAR}")

    categories = _pick_multi("[1] 원하는 옷 카테고리를 선택하세요 (복수 선택 가능)", _CATEGORY_OPTIONS)
    styles = _pick_multi("[2] 선호하는 스타일을 선택하세요 (복수 선택 가능)", _STYLE_OPTIONS)

    print("\n[3] 선호하는 브랜드가 있으면 입력하세요 (선택사항)")
    print("  예: 나이키, 아디다스, 컨버스 · 없으면 Enter")
    brand_raw = input("\n브랜드 입력: ").strip()
    brands = [b.strip() for b in brand_raw.split(",") if b.strip()] if brand_raw else []

    feels = _pick_multi("[4] 원하는 느낌을 선택하세요 (선택사항, 복수 선택 가능)", _FEEL_OPTIONS)

    print("\n[5] 가격대를 선택하세요 (선택사항)")
    print(LINE)
    for number, label, _ in _PRICE_OPTIONS:
        print(f"  {number}. {label}")
    price_raw = input("\n선택 (번호 하나만, 예: 2 또는 0): ").strip()
    budget_min = budget_max = None
    budget_label = None
    for number, label, budget in _PRICE_OPTIONS:
        if price_raw == number and budget is not None:
            budget_min, budget_max = budget
            budget_label = label

    extra = input("\n💬 추가로 원하는 스타일 설명이 있으면 자연어로 입력하세요 (없으면 Enter): ").strip()
    keywords = [extra] if extra else []

    profile = PreferenceProfile(
        raw_input=extra or ", ".join(categories + styles + brands + feels),
        styles=styles,
        brands=brands,
        categories=categories,
        feels=feels,
        keywords=keywords,
        budget_label=budget_label,
        budget_min=budget_min,
        budget_max=budget_max,
    )

    print(f"\n📋 선택한 취향 요약")
    print(LINE)
    if categories:
        print(f"  카테고리: {', '.join(categories)}")
    if styles:
        print(f"  스타일: {', '.join(styles)}")
    if brands:
        print(f"  브랜드: {', '.join(brands)}")
    if feels:
        print(f"  느낌: {', '.join(feels)}")
    if budget_label:
        print(f"  가격대: {budget_label}")
    return profile


# --- 메뉴 액션 ---


def run_comparison(container: ServiceContainer) -> None:
    print(f"\n{LINE}\n📊 제품 가격 및 평점 비교 분석\n{LINE}")
    print("비교할 제품 2개 이상을 입력해주세요.")
    print("예: '나이키 에어포스 1 vs 아디다스 삼바' 또는 'A 코트와 B 코트'")

    query = input("\n제품 입력: ").strip()
    if not query:
        print("⚠️ 제품명을 입력해주세요.")
        return

    print(f"\n🔍 비교 분석 중: {query}")
    report = container.comparison.compare(query)
    print(f"\n{BAR}\n{render_comparison(report)}\n{BAR}")


def run_recommendation(container: ServiceContainer) -> None:
    print(f"\n{LINE}\n🎯 취향 기반 제품 추천\n{LINE}")
    print("취향 키워드를 입력해주세요.")
    print("예: '미니멀리즘, 30만원대, 아르켓 느낌' 또는 '스트릿 후드 10만원 이하'")

    preference = input("\n취향 입력: ").strip()
    if not preference:
        print("⚠️ 취향 키워드를 입력해주세요.")
        return

    print(f"\n🔍 추천 제품 검색 중: {preference}")
    result = container.recommendation.recommend(preference)
    print(f"\n{BAR}\n{render_recommendation(result)}\n{BAR}")


def run_review_summary(container: ServiceContainer) -> None:
    print(f"\n{LINE}\n📝 제품 리뷰 기반 장단점 요약\n{LINE}")
    print("분석할 제품명을 입력해주세요. 예: '나이키 에어맥스'")

    product_name = input("\n제품명 입력: ").strip()
    if not product_name:
        print("⚠️ 제품명을 입력해주세요.")
        return

    print(f"\n🔍 리뷰 수집·분석 중: {product_name}")
    summary = container.review_summary.summarize(product_name)
    print(f"\n{BAR}\n{render_review_summary(summary)}\n{BAR}")


def run_wizard_recommendation(container: ServiceContainer) -> None:
    profile = run_wizard()
    print("\n🔍 선택하신 취향으로 제품을 검색합니다...")
    result = container.recommendation.recommend(profile=profile)
    print(f"\n{BAR}\n{render_recommendation(result)}\n{BAR}")


# --- 진입점 ---


def _ensure_container() -> ServiceContainer:
    """컨테이너를 조립한다. API 키가 없으면 안내 후 입력받는다."""
    load_dotenv()
    try:
        return build_container()
    except ValueError:
        print("⚠️ 환경변수 TAVILY_API_KEY가 설정되지 않았습니다.")
        print("  → 프로젝트 폴더에 .env 파일을 만들고 TAVILY_API_KEY=키값 을 넣어주세요.")
        key = input("TAVILY_API_KEY를 직접 입력하세요 (Enter로 종료): ").strip()
        if not key:
            print("프로그램을 종료합니다.")
            sys.exit(0)
        os.environ["TAVILY_API_KEY"] = key
        return build_container(settings=Settings())


_MENU = """
{bar}
🛍️  무신사 쇼핑 도움 에이전트
{bar}
1. 제품 가격 및 평점 비교 분석
2. 사용자 취향 기반 제품 추천
3. 제품 리뷰 기반 장단점 요약
4. 취향 기반 제품 추천 (인터랙티브)
5. 종료
{bar}"""

_ACTIONS = {
    "1": run_comparison,
    "2": run_recommendation,
    "3": run_review_summary,
    "4": run_wizard_recommendation,
}


def main() -> None:
    logging.basicConfig(level=logging.WARNING)
    container = _ensure_container()

    while True:
        print(_MENU.format(bar=BAR))
        try:
            choice = input("\n원하는 기능을 선택하세요 (1-5): ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\n\n👋 프로그램을 종료합니다. 감사합니다!")
            return

        if choice == "5":
            print("\n👋 프로그램을 종료합니다. 감사합니다!")
            return

        action = _ACTIONS.get(choice)
        if action is None:
            print("⚠️ 1부터 5 사이의 숫자를 입력해주세요.")
            continue

        try:
            action(container)
        except KeyboardInterrupt:
            print("\n(작업을 취소했습니다)")
        except ValueError as exc:
            print(f"⚠️ {exc}")
        except SearchUnavailableError as exc:
            print(f"🚧 검색 백엔드가 일시적으로 사용 불가합니다: {exc}")
        except SearchError as exc:
            print(f"❌ 검색 중 오류가 발생했습니다: {exc}")
        except Exception as exc:  # CLI 는 어떤 오류에도 죽지 않는다
            print(f"❌ 예상치 못한 오류: {exc}")


if __name__ == "__main__":
    main()
