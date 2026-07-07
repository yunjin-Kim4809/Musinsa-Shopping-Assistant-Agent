"""비정형 검색 텍스트에서 구조화 정보(가격/평점/예산/제품명)를 추출한다.

웹 검색 결과는 형식이 제각각이라 정규식 + 문맥 필터의 조합으로 방어적으로 파싱한다.
모든 함수는 실패 시 예외 대신 None 필드를 반환한다 (부분 정보라도 살리는 방침).
"""

from __future__ import annotations

import re

from app.domain.models import PriceInfo, RatingInfo

# 상식적인 의류 가격 범위 (이 밖의 숫자는 가격이 아닐 가능성이 높음)
PRICE_MIN, PRICE_MAX = 5_000, 5_000_000

_NUM = r"(\d{1,3}(?:,\d{3})+|\d{4,7})"  # 12,345 또는 12345 형태

# '가격'을 지칭하는 라벨이 붙은 금액 (신뢰도 높음)
_CURRENT_PRICE_RE = re.compile(
    rf"(?:판매가|현재가|최저가|할인가|최종가|가격)\s*[:은는]?\s*{_NUM}\s*원"
)
_ORIGINAL_PRICE_RE = re.compile(
    rf"(?:정가|원가|소비자가|할인\s*전\s*가격?)\s*[:은는]?\s*{_NUM}\s*원"
)
# 라벨 없는 일반 금액 (문맥 필터를 거쳐 사용)
_GENERIC_PRICE_RE = re.compile(rf"(?:₩\s*{_NUM}|{_NUM}\s*원)")

# 금액 주변에 이런 단어가 있으면 가격이 아닐 가능성이 높다
_PRICE_EXCLUDE_NEARBY = (
    "리뷰", "후기", "평점", "별점", "배송비", "적립", "포인트",
    "조회", "판매량", "재고", "년", "월", "일",
)

_DISCOUNT_RE = re.compile(r"(\d{1,2})\s*%\s*(?:할인|OFF|DC|SALE|↓)", re.IGNORECASE)
_SHIPPING_RE = re.compile(rf"배송비?\s*[:]?\s*{_NUM}\s*원")

_RATING_RES = (
    re.compile(r"(?:평점|별점|만족도)\s*[:]?\s*([0-5](?:\.\d{1,2})?)\s*(?:/\s*5|점)?"),
    re.compile(r"([0-5](?:\.\d{1,2})?)\s*/\s*5(?:\.0)?(?:점)?"),
    re.compile(r"([0-5]\.\d{1,2})\s*점"),
)
# 리뷰 수는 가격과 달리 작은 수(수십~수백)도 유효하다
_COUNT = r"(\d{1,3}(?:,\d{3})+|\d{1,7})"
_REVIEW_COUNT_RE = re.compile(rf"(?:리뷰|후기|상품평)\s*[:]?\s*{_COUNT}\s*(?:개|건)?")

# 제품명 구분자: "A vs B", "A, B", "A와 B" (와/과는 뒤에 공백이 있을 때만 접속사로 간주
# → "화이트와 푸마"는 분리되고 "스니커즈와이드"처럼 단어 내부의 '와'는 보존된다)
_PRODUCT_SEPARATOR_RE = re.compile(
    r"\s+vs\.?\s+|\s*,\s*|(?<=[가-힣a-zA-Z0-9)\]])[와과]\s+",
    re.IGNORECASE,
)

_BUDGET_RANGE_RE = re.compile(r"(\d{1,4})\s*[~∼-]\s*(\d{1,4})\s*만\s*원")
_BUDGET_BAND_RE = re.compile(r"(\d{1,4})\s*만\s*원\s*대")
_BUDGET_UNDER_RE = re.compile(r"(\d{1,4})\s*만\s*원\s*이하")
_BUDGET_OVER_RE = re.compile(r"(\d{1,4})\s*만\s*원\s*이상")
_BUDGET_EXACT_RE = re.compile(r"(\d{1,4})\s*만\s*원")


def _to_int(number_text: str) -> int:
    return int(number_text.replace(",", ""))


def _plausible(price: int) -> bool:
    return PRICE_MIN <= price <= PRICE_MAX


def split_product_names(query: str) -> list[str]:
    """비교 질의에서 제품명들을 분리한다.

    >>> split_product_names("나이키 에어포스 화이트와 푸마 스웨이드")
    ['나이키 에어포스 화이트', '푸마 스웨이드']
    """
    parts = _PRODUCT_SEPARATOR_RE.split(query)
    return [p.strip() for p in parts if p and p.strip()]


def extract_price_info(text: str) -> PriceInfo:
    """텍스트에서 가격 정보를 추출한다.

    전략: ① 라벨 붙은 금액(판매가/정가 등)을 최우선 신뢰
         ② 없으면 라벨 없는 금액 중 주변 문맥이 깨끗한 것을 사용
         ③ 할인율·정가·현재가 사이의 산술 관계로 빈 필드를 역산
    """
    info = PriceInfo()

    labeled_current = [
        p for m in _CURRENT_PRICE_RE.finditer(text) if _plausible(p := _to_int(m.group(1)))
    ]
    labeled_original = [
        p for m in _ORIGINAL_PRICE_RE.finditer(text) if _plausible(p := _to_int(m.group(1)))
    ]

    if labeled_current:
        # 같은 제품의 여러 표기 중 최솟값 = 실제 판매가(할인가)일 가능성이 높다
        info.current = min(labeled_current)
    else:
        candidates = []
        for match in _GENERIC_PRICE_RE.finditer(text):
            price = _to_int(match.group(1) or match.group(2))
            if not _plausible(price):
                continue
            # 금액 바로 앞뒤 10자 문맥에 배제 키워드가 있으면 가격으로 보지 않는다
            context = text[max(0, match.start() - 10) : match.end() + 10]
            if any(word in context for word in _PRICE_EXCLUDE_NEARBY):
                continue
            candidates.append(price)
        if candidates:
            info.current = min(candidates)

    if labeled_original:
        original = max(labeled_original)
        if info.current is None or original >= info.current:
            info.original = original

    discounts = [int(m.group(1)) for m in _DISCOUNT_RE.finditer(text) if 1 <= int(m.group(1)) <= 99]
    if discounts:
        info.discount_rate = float(max(discounts))

    # 산술 관계로 보완
    if info.current and info.discount_rate and not info.original:
        info.original = round(info.current / (1 - info.discount_rate / 100))
    elif info.current and info.original and info.original > info.current and not info.discount_rate:
        info.discount_rate = round((1 - info.current / info.original) * 100, 1)

    if "무료배송" in text or "무료 배송" in text:
        info.shipping_cost = 0
    else:
        shipping_match = _SHIPPING_RE.search(text)
        if shipping_match:
            shipping = _to_int(shipping_match.group(1))
            if shipping <= 50_000:
                info.shipping_cost = shipping

    return info


def extract_rating_info(text: str) -> RatingInfo:
    """텍스트에서 평점(5점 만점)과 리뷰 수를 추출한다."""
    info = RatingInfo()

    ratings: list[float] = []
    for pattern in _RATING_RES:
        for match in pattern.finditer(text):
            value = float(match.group(1))
            if 0 <= value <= 5:
                ratings.append(value)
        if ratings:
            break  # 신뢰도 높은 패턴에서 찾았으면 다음 패턴은 생략

    if ratings:
        info.rating = round(sum(ratings) / len(ratings), 2)

    counts = [_to_int(m.group(1)) for m in _REVIEW_COUNT_RE.finditer(text)]
    if counts:
        info.review_count = max(counts)

    return info


def parse_budget(text: str) -> tuple[int | None, int | None, str | None]:
    """예산 표현을 (최소, 최대, 라벨) 로 파싱한다.

    지원: "20~30만원", "30만원대", "50만원 이하", "10만원 이상", "30만원"
    """
    if match := _BUDGET_RANGE_RE.search(text):
        low, high = int(match.group(1)), int(match.group(2))
        if low > high:
            low, high = high, low
        return low * 10_000, high * 10_000, f"{low}~{high}만원"

    if match := _BUDGET_BAND_RE.search(text):
        band = int(match.group(1))
        # "30만원대" == 30만~40만 미만
        return band * 10_000, (band + 10) * 10_000, f"{band}만원대"

    if match := _BUDGET_UNDER_RE.search(text):
        limit = int(match.group(1))
        return None, limit * 10_000, f"{limit}만원 이하"

    if match := _BUDGET_OVER_RE.search(text):
        limit = int(match.group(1))
        return limit * 10_000, None, f"{limit}만원 이상"

    if match := _BUDGET_EXACT_RE.search(text):
        amount = int(match.group(1))
        return amount * 10_000, amount * 10_000, f"{amount}만원"

    return None, None, None


_SPEC_KEYWORDS = ("소재", "재질", "원단", "사이즈", "컬러", "색상", "핏", "기능", "혼용률")


def extract_specs(texts: list[str], max_items: int = 3) -> str:
    """검색 결과 본문에서 스펙으로 보이는 줄을 추려 요약한다."""
    seen: set[str] = set()
    specs: list[str] = []

    for text in texts:
        for line in text.splitlines():
            line = line.strip()
            if not (10 <= len(line) <= 150):
                continue
            if any(keyword in line for keyword in _SPEC_KEYWORDS) and line not in seen:
                seen.add(line)
                specs.append(line)
                if len(specs) >= max_items:
                    return " | ".join(specs)

    if specs:
        return " | ".join(specs)

    # 스펙 라인을 못 찾으면 첫 결과 앞부분으로 대체
    for text in texts:
        snippet = text.strip()
        if snippet:
            return snippet[:150] + ("..." if len(snippet) > 150 else "")
    return "스펙 정보 없음"
