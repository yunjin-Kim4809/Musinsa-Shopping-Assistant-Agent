# 리팩터링 작업 내역

해커톤 출품작(CLI 스크립트 4개)을 프로덕션 수준 백엔드로 재구축한 전 과정의 기록입니다.

## 요약

| 항목 | Before | After |
|------|--------|-------|
| 구조 | 평면 스크립트 4개 (1,900줄) | 5계층 패키지 (domain/infra/analysis/services/api) |
| 인터페이스 | CLI 메뉴만 | REST API (FastAPI) + CLI |
| 외부 호출 | 매번 순차 호출, 실패 시 print 후 계속 | 캐시·singleflight·재시도·rate limit·서킷 브레이커 + 병렬화 |
| 랭킹 | 키워드 존재 시 +N점 가산 | BM25 (IDF·TF 포화·길이 정규화) + 규칙 가산 |
| 감성 분석 | 키워드 리스트 순회 `in` 검사 | Aho-Corasick 1회 스캔 + 극성 스팬 억제 |
| 테스트 | 0개 | **150개** (네트워크·API 키 불필요, 퍼즈 테스트 포함) |
| 품질 도구 | 없음 | ruff 린트 + GitHub Actions CI + Dockerfile |
| 패키징 | requirements.txt 3줄 | pyproject.toml + 콘솔 스크립트 |
| 보안 | `.env` 가 git 에 커밋됨 | 추적 제거 + .env.example 템플릿 |

## 시작 시점에 발견된 문제

1. **깨진 의존성**: `main.py` 가 import 하는 `취향기반추천.py` 가 저장소에 없었다
   (컴파일된 `.pyc` 만 `__pycache__` 에 커밋되어 있음). 4번 메뉴는 사실상 실행 불가.
2. **`.env` 가 git 추적 상태**: `.gitignore` 가 비어 있어 API 키 파일이 저장소에
   올라가는 구조였다 (다행히 플레이스홀더 상태였음).
3. **`__pycache__` 커밋**: 바이트코드가 저장소에 포함.
4. **로직 중복**: 가격 추출·무신사 필터링·검색 호출 코드가 3개 파일에 조금씩
   다르게 복사되어 있었다.
5. **취약한 제품명 분리**: `"화이트와 푸마".split("와")` 방식이라
   "스니커즈**와**이드" 같은 단어 내부의 '와'에서 오동작.
6. **에러 처리 부재**: 검색 실패 시 `print` 후 진행 → 부분 데이터로 잘못된 비교 결과 생성.

## 작업 단계 (커밋 순)

### 1단계 — 저장소 위생 · 패키징 (`chore`)

- `.env`, `__pycache__` git 추적 제거, `.gitignore` 정비
- `.env.example` 템플릿 (튜닝 가능한 설정값 문서화 포함)
- `pyproject.toml`: 메타데이터, 의존성, `musinsa-agent` 콘솔 스크립트, pytest 설정

### 2단계 — 인프라 계층 (`feat`)

외부 검색 API 호출을 안정화하는 부품 4종 + 조합 클라이언트:

- **TTL-LRU 캐시**: 해시맵 + 이중 연결 리스트 직접 구현 (O(1) get/put),
  lazy expiration, 적중률 통계
- **토큰 버킷**: lazy refill, 필요 대기 시간 계산 방식 (busy-wait 없음)
- **서킷 브레이커**: CLOSED/OPEN/HALF_OPEN 상태 머신, 동시 프로브 제한
- **재시도**: 지수 백오프 + full jitter, `CircuitOpenError` 는 재시도 제외
- **TavilySearchClient**: 캐시→재시도→토큰버킷→서킷 순 계층 조합,
  ThreadPoolExecutor 병렬 fan-out, 부분 성공 허용, `stats()` 관측 노출

모든 부품에 가짜 시계/슬립을 주입하는 방식으로 시간 의존 없는 단위 테스트 39건.

### 3단계 — 분석 계층 (`feat`)

- **Aho-Corasick 자동자**: 트라이 + BFS 실패 링크. naive 구현과의 대조 테스트로 검증
- **Okapi BM25**: Lucene 변형 IDF(음수 방지), 힙 기반 top-k
- **음절 bigram 토크나이저**: 형태소 분석기 없이 한국어 부분 일치 근사
- **Levenshtein**: 2행 롤링 DP + 임계값 조기 종료
- **추출기**: 가격(라벨 우선 + 문맥 배제 필터)/평점/예산/제품명 분리 정규식 파서
  - 제품명 분리를 "'와/과' 뒤에 공백이 올 때만 접속사"로 교정
- **사전(lexicons)**: 감성/주제/스타일/브랜드 한국어 사전
- 도메인 모델 (dataclass, 외부 의존성 없음)

### 4단계 — 서비스 계층 (`feat`)

- **ReviewSummaryService**: AC 1회 스캔 감성·주제 분석, 반대 극성 스팬 억제,
  준중복 문장 제거, 주제당 상한(정보 다양성)
- **RecommendationService**: 프로필 파싱 → 쿼리 생성 → 병렬 수집 → 준중복 제거
  → BM25+규칙 랭킹 → 이유 생성 파이프라인
- **ComparisonService**: N개(2~4) 제품 비교로 일반화, 무신사 우선 + 폴백
- **ReasonGenerator 전략 패턴**: OpenAI ↔ 휴리스틱 자동 폴백
- 마크다운 렌더링을 별도 모듈로 분리 (CLI/API 공용)

### 5단계 — API · CLI (`feat`)

- FastAPI 앱 팩토리 + composition root (테스트 주입 가능)
- 예외→HTTP 매핑: 400(입력)/503+Retry-After(서킷 OPEN)/502(업스트림)/422(검증)
- 요청 ID + 처리 시간 로깅 미들웨어, Swagger 자동 문서
- `/api/v1/stats`: 캐시 적중률·서킷 상태·호출 수 실시간 관측
- CLI 재작성 + **소실된 인터랙티브 위저드 복원** — `.pyc` 를 `marshal` 로 역직렬화해
  코드 객체의 상수(메뉴 선택지, GPT 프롬프트)를 추출, 원본 UX 를 재현
- 레거시 스크립트 3종 삭제, `main.py` 는 하위 호환 진입점으로 유지

### 6단계 — 문서화 (`docs`)

- README 전면 개편 (아키텍처 다이어그램, CS 기술 표, API 예시)
- ARCHITECTURE.md (설계 + 알고리즘 심화 + ADR)
- 본 문서 (WORK_LOG.md)

## 검증

```bash
$ python -m pytest tests/
139 passed in 0.20s        # 네트워크·API 키 불필요
```

스모크 테스트 (더미 API 키로 서버 기동):

- `GET /health` → 200, `GET /docs` Swagger 정상
- `POST /api/v1/compare {"query": "제품하나"}` → **400** (제품 2개 필요 안내)
- `POST /api/v1/compare {}` → **422** (pydantic 검증)
- 더미 키로 검색 시도 → 인증 실패 반복 → **서킷 브레이커 OPEN**
  → `503 + Retry-After` 응답, `/api/v1/stats` 에서 `"state": "open"` 관측 확인
- CLI 메뉴/위저드 동작 확인

## 트러블슈팅 기록 (실제 겪은 문제들)

1. **가격 배제 필터의 문맥 윈도우**: "리뷰 12,000개 돌파! … 45,000원" 에서
   윈도우 20자가 멀리 있는 "리뷰"까지 잡아 정상 가격을 배제 → 10자로 축소.
2. **단음절 키워드의 부분 매칭 함정**: 주제 사전의 "품"이 "제**품**", "**품**질"에,
   "울"이 "겨**울**"에 매칭되어 주제 오분류 → 모호한 단음절 키워드를 사전에서 제거.
   (Aho-Corasick 같은 부분 문자열 매칭에서 사전 설계가 알고리즘만큼 중요하다는 교훈)
3. **한국어 불규칙 활용**: "느리→느려"(르활용), "아쉽→아쉬워"(ㅂ불규칙)는 어간
   표기가 변해 매칭 실패 → 대표 활용형을 사전에 추가.
4. **소실된 모듈 복원**: 원본 `취향기반추천.py` 없이 `.pyc` 만 존재
   → `marshal.loads` 로 코드 객체를 읽어 `co_consts` 에서 메뉴 구조·프롬프트 복원.

## 7단계 — 2차 개선 라운드 (`feat`/`chore`)

1차 리팩터링에서 "한계"로 기록했던 항목 중 실현 가치가 높은 것들을 구현:

- **Singleflight 패턴** (`infra/singleflight.py`): 동일 키의 동시 캐시 미스를
  원격 호출 1회로 병합 (Go `golang.org/x/sync/singleflight` 패턴).
  리더의 예외도 팔로워에게 전파해 실패 시 stampede 재발을 방지.
  통합 테스트로 "동시 요청 8개 → 원격 호출 1회" 검증.
- **API 자체 rate limit 미들웨어**: 클라이언트(IP)별 토큰 버킷으로 429 +
  Retry-After 응답. 버킷 저장소로 자체 TTL-LRU 캐시를 재사용해 메모리 유계 유지.
- **퍼즈 테스트** (`tests/test_fuzz.py`): 고정 시드 무작위 입력 800케이스로
  Aho-Corasick ↔ 브루트포스, 최적화 Levenshtein ↔ 전체 테이블 DP 대조.
  거리 함수 공리(대칭성·삼각 부등식) 검증 포함.
- **ruff 린트** 도입 및 전체 코드 정리 (import 정렬, 최신 문법 등 25건)
- **GitHub Actions CI**: Python 3.10/3.12/3.13 매트릭스 테스트 + 린트
- **Dockerfile**: 의존성 레이어 캐싱, 비루트 사용자, HEALTHCHECK 포함

테스트: 139개 → **150개**.

## 이후 확장 아이디어

- Redis 캐시/분산 rate limit (다중 인스턴스 환경)
- 무신사 구조화 데이터 소스 연동 (검색 스니펫 의존 탈피)
- 소형 한국어 감성 분류 모델 도입 (사전 기반의 한계 보완)
- 사용자 세션·선호 이력 기반 개인화 랭킹
