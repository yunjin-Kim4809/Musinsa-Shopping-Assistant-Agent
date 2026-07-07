<div align="center">

# 🛍️ 무신사 쇼핑 도움 에이전트

### Musinsa Shopping Assistant Agent

**가격 비교 · 취향 추천 · 리뷰 요약**을 제공하는 쇼핑 에이전트 백엔드

[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-REST%20API-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Tests](https://img.shields.io/badge/tests-139%20passed-brightgreen)]()
[![Coverage](https://img.shields.io/badge/mock-network--free%20tests-blue)]()

*HateSlop 미니 Agent 해커톤 출품작을 프로덕션 수준 백엔드로 리팩터링한 프로젝트*

</div>

---

## ✨ 무엇을 하나요?

| 기능 | 설명 | 엔드포인트 |
|------|------|-----------|
| 🥇 **가격·평점 비교** | 2~4개 제품의 가격/할인/평점/스펙을 수집해 **가성비 순** 비교 리포트 생성 | `POST /api/v1/compare` |
| 🎯 **취향 기반 추천** | 자유 형식 취향("미니멀, 30만원대, 아르켓 느낌")을 파싱해 **BM25 랭킹**으로 추천 | `POST /api/v1/recommendations` |
| 📝 **리뷰 장단점 요약** | 무신사 리뷰를 수집해 **Aho-Corasick 감성 분석**으로 주제별 장단점 요약 | `POST /api/v1/reviews/summary` |
| 📊 **운영 지표** | 캐시 적중률, 서킷 브레이커 상태, 원격 호출 수 실시간 관측 | `GET /api/v1/stats` |

동일한 서비스 계층을 **REST API**와 **대화형 CLI** 두 인터페이스로 제공합니다.

---

## 🏗️ 아키텍처

```
        ┌──────────────┐          ┌──────────────┐
        │  REST API    │          │  CLI (메뉴/   │
        │  (FastAPI)   │          │  취향 위저드) │
        └──────┬───────┘          └──────┬───────┘
               └──────────┬──────────────┘
                          ▼
        ┌─────────────────────────────────────────┐
        │              서비스 계층                 │
        │  비교 분석 │ 취향 추천 │ 리뷰 요약        │
        └──────┬──────────────────────┬───────────┘
               ▼                      ▼
   ┌───────────────────────┐  ┌───────────────────────┐
   │       분석 계층        │  │      인프라 계층       │
   │ Aho-Corasick · BM25   │  │ TTL-LRU 캐시 · 토큰버킷 │
   │ Levenshtein · 추출기  │  │ 서킷브레이커 · 재시도    │
   └───────────┬───────────┘  └───────────┬───────────┘
               ▼                          ▼
        ┌──────────────┐          ┌──────────────┐
        │  도메인 모델  │          │  Tavily API  │
        └──────────────┘          └──────────────┘
```

외부 검색 API 호출은 4겹의 안정화 계층을 거칩니다:

```
캐시 조회 → [miss] → 재시도(지수 백오프+jitter) → 토큰 버킷 → 서킷 브레이커 → 원격 호출
```

## 🧠 적용된 CS 기술

| 기술 | 사용처 | 핵심 |
|------|--------|------|
| **TTL-LRU 캐시** | 검색 결과 캐싱 | 해시맵 + 이중 연결 리스트, O(1) get/put, lazy expiration |
| **토큰 버킷** | API 호출 속도 제한 | lazy refill, 버스트 허용 + 장기 평균속도 제한 |
| **서킷 브레이커** | 외부 장애 격리 | CLOSED/OPEN/HALF_OPEN 상태 머신, 장애 전파 차단 |
| **지수 백오프 + full jitter** | 일시 장애 재시도 | thundering herd 방지 (AWS 권장 방식) |
| **Aho-Corasick** | 리뷰 감성/주제 분석 | 수백 개 키워드를 텍스트 1회 스캔으로 매칭, O(n+z) |
| **Okapi BM25** | 추천 관련도 랭킹 | IDF·TF 포화·문서 길이 정규화, 힙 top-k O(n log k) |
| **Levenshtein 거리** | 준중복 상품/문장 제거 | 2행 롤링 DP, O(min(m,n)) 공간, 임계값 조기 종료 |
| **스레드풀 병렬화** | 다중 검색 fan-out | I/O 바운드 병렬화 (GIL 무관), 지연 ≈ 최장 쿼리 1개 |

> 각 기술의 **왜/어떻게/트레이드오프**는 [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)에 상세히 정리되어 있습니다.

---

## 🚀 빠른 시작

### 1. 설치

```bash
git clone https://github.com/yxzkng/Musinsa-Shopping-Assistant-Agent.git
cd Musinsa-Shopping-Assistant-Agent

python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

### 2. API 키 설정

```bash
cp .env.example .env
# .env 파일을 열어 TAVILY_API_KEY 입력 (필수)
# OPENAI_API_KEY 는 선택 — 없으면 휴리스틱 추천 이유로 자동 대체
```

| 키 | 필수 | 발급처 | 용도 |
|----|:---:|--------|------|
| `TAVILY_API_KEY` | ✅ | [tavily.com](https://tavily.com) | 웹 검색 |
| `OPENAI_API_KEY` | 🔸 | [platform.openai.com](https://platform.openai.com) | LLM 추천 이유 생성 (선택) |

### 3. 실행

**대화형 CLI**

```bash
python main.py
```

**REST API 서버**

```bash
python -m app.api
# 또는: uvicorn "app.api.app:create_app" --factory --reload
```

서버 실행 후 **http://127.0.0.1:8000/docs** 에서 Swagger UI로 바로 테스트할 수 있습니다.

---

## 📡 API 사용 예시

<details>
<summary><b>🥇 제품 비교</b> — <code>POST /api/v1/compare</code></summary>

```bash
curl -X POST http://127.0.0.1:8000/api/v1/compare \
  -H "Content-Type: application/json" \
  -d '{"query": "나이키 에어포스 1 vs 아디다스 삼바"}'
```

```json
{
  "query": "나이키 에어포스 1 vs 아디다스 삼바",
  "winner": "나이키 에어포스 1",
  "winner_reason": "가성비 점수 92.3점으로 최고, 비교 대상 중 최저가",
  "products": [
    {
      "name": "나이키 에어포스 1",
      "price": {"current": 139000, "discount_rate": 10.0},
      "rating": {"rating": 4.8, "review_count": 12000},
      "value_score": 92.3
    }
  ],
  "markdown": "### 🛍️ 나이키 에어포스 1 vs 아디다스 삼바 비교 분석\n..."
}
```
</details>

<details>
<summary><b>🎯 취향 추천</b> — <code>POST /api/v1/recommendations</code></summary>

```bash
curl -X POST http://127.0.0.1:8000/api/v1/recommendations \
  -H "Content-Type: application/json" \
  -d '{"preference": "미니멀리즘, 30만원대, 아르켓 느낌", "top_k": 3}'
```

```json
{
  "profile": {
    "styles": ["미니멀"],
    "brands": ["아르켓"],
    "budget_label": "30만원대",
    "budget_min": 300000,
    "budget_max": 400000
  },
  "products": [
    {
      "name": "울 발마칸 코트",
      "price": 329000,
      "is_musinsa": true,
      "score": 87.5,
      "reason": "미니멀 스타일과 잘 맞습니다 · 예산(30만원대)에 부합합니다"
    }
  ]
}
```
</details>

<details>
<summary><b>📝 리뷰 요약</b> — <code>POST /api/v1/reviews/summary</code></summary>

```bash
curl -X POST http://127.0.0.1:8000/api/v1/reviews/summary \
  -H "Content-Type: application/json" \
  -d '{"product_name": "나이키 에어맥스"}'
```

```json
{
  "product_name": "나이키 에어맥스",
  "source_count": 14,
  "pros": [
    {"topic": "착용감", "sentence": "쿠션이 좋아 하루 종일 신어도 편안해요", "polarity": 1}
  ],
  "cons": [
    {"topic": "핏/사이즈", "sentence": "정사이즈보다 반 치수 크게 나온 느낌이에요", "polarity": -1}
  ]
}
```
</details>

<details>
<summary><b>📊 운영 지표</b> — <code>GET /api/v1/stats</code></summary>

```json
{
  "search": {
    "cache": {"hits": 42, "misses": 18, "hit_rate": 0.7},
    "circuit_breaker": {"state": "closed", "consecutive_failures": 0},
    "rate_limiter_tokens": 8.4,
    "remote_calls": 18,
    "remote_failures": 0
  }
}
```
</details>

---

## 📁 프로젝트 구조

```
app/
├── config.py               # pydantic-settings 기반 설정
├── domain/                 # 순수 도메인 모델 (외부 의존성 없음)
├── infra/                  # 외부 호출 안정화 부품
│   ├── cache.py            #   TTL-LRU 캐시 (해시맵 + 이중 연결 리스트)
│   ├── rate_limiter.py     #   토큰 버킷
│   ├── circuit_breaker.py  #   서킷 브레이커 상태 머신
│   ├── retry.py            #   지수 백오프 + full jitter
│   └── search_client.py    #   부품 조합 + 병렬 검색 클라이언트
├── analysis/               # 문자열 알고리즘 / IR
│   ├── aho_corasick.py     #   다중 패턴 매칭 자동자
│   ├── bm25.py             #   Okapi BM25 랭킹
│   ├── tokenizer.py        #   한국어 음절 bigram 토크나이저
│   ├── similarity.py       #   Levenshtein 편집 거리
│   ├── extractors.py       #   가격/평점/예산 정규식 추출기
│   └── lexicons.py         #   감성/주제/스타일 사전
├── services/               # 비즈니스 로직 (3개 에이전트)
├── api/                    # FastAPI (라우트/스키마/DI/미들웨어)
└── cli.py                  # 대화형 CLI + 취향 위저드

tests/                      # 139개 테스트 (네트워크 불필요)
docs/
├── ARCHITECTURE.md         # 설계 문서 + CS 기술 심화
└── WORK_LOG.md             # 리팩터링 작업 내역
```

## 🧪 테스트

전 테스트가 **네트워크·API 키 없이** 실행됩니다 (가짜 시계·가짜 검색 클라이언트 주입).

```bash
pip install pytest httpx
python -m pytest tests/ -v
# 139 passed
```

---

## 📚 문서

| 문서 | 내용 |
|------|------|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | 계층 설계, CS 알고리즘 상세(복잡도·트레이드오프), 설계 결정 기록 |
| [docs/WORK_LOG.md](docs/WORK_LOG.md) | 해커톤 코드 → 현재까지의 리팩터링 전 과정 |

## 🔧 기술 스택

**Python 3.10+** · **FastAPI** · **pydantic v2** · **Tavily Search API** · **OpenAI API**(선택) · **pytest**

---

<div align="center">
<sub>🏆 HateSlop 미니 Agent 해커톤 출품작 기반</sub>
</div>
