<div align="center">

# 🛍️ 무신사 쇼핑 도움 에이전트

### *Musinsa Shopping Assistant Agent*

당신의 무신사 쇼핑을 똑똑하게 도와주는 AI 에이전트

<br>

> 🏆 **HateSlop 미니 Agent 해커톤**을 위해 제작되었습니다.

</div>

---

## ✨ 주요 기능

<table>
<tr>
<th align="center">메뉴</th>
<th align="left">기능</th>
<th align="left">설명</th>
</tr>
<tr>
<td align="center">🥇 <b>1</b></td>
<td><b>제품 가격·평점 비교</b></td>
<td>두 제품의 가격, 할인, 평점, 스펙을 비교하고 <b>가성비 순</b>으로 추천</td>
</tr>
<tr>
<td align="center">🎯 <b>2</b></td>
<td><b>취향 기반 제품 추천</b></td>
<td>한 줄 키워드(스타일, 예산, 브랜드)로 무신사 위주 추천 <b>3개</b></td>
</tr>
<tr>
<td align="center">📝 <b>3</b></td>
<td><b>리뷰 장단점 요약</b></td>
<td>제품명 입력 시 무신사 리뷰를 수집해 주제별 <b>장단점</b> 요약</td>
</tr>
<tr>
<td align="center">🤖 <b>4</b></td>
<td><b>취향 기반 추천 (인터랙티브)</b></td>
<td>카테고리·스타일·브랜드 선택 후 <b>GPT-4o</b>로 관련성 점수 부여해 상위 5개 추천</td>
</tr>
</table>

---

## 📋 요구 사항

| 항목 | 필수 여부 | 발급처 |
|------|:--------:|--------|
| 🐍 **Python 3.8+** | ✅ 필수 | — |
| 🔑 **TAVILY_API_KEY** | ✅ 필수 | [Tavily](https://tavily.com) |
| 🔑 **OPENAI_API_KEY** | 🔸 선택 (4번 메뉴용) | [OpenAI](https://platform.openai.com) |

---

## 🚀 설치 및 실행

### 1️⃣ 저장소 클론 및 의존성 설치

```bash
cd hateslop_agent_hackathon
pip install -r requirements.txt
```

### 2️⃣ API 키 설정

프로젝트 폴더에 **`.env`** 파일을 만들고 아래 형식으로 입력합니다.

```env
TAVILY_API_KEY=여기에_타빌리_API_키
OPENAI_API_KEY=여기에_오픈AI_API_키
```

> 💡 **Tip**
> - `1·2·3`번만 쓸 경우 → `TAVILY_API_KEY`만 있어도 OK
> - `4`번(인터랙티브 추천)을 쓰려면 → `OPENAI_API_KEY`도 필요

### 3️⃣ 실행

```bash
python main.py
```

실행 후 메뉴에서 원하는 번호를 입력하면 됩니다. 🎉

---

## 📁 프로젝트 구조

```
hateslop_agent_hackathon/
├── 📄 main.py                          # 진입점, 메뉴 및 API 키 처리
├── 🥇 price_rating_comparison.py       # 1번: 가격·평점 비교 에이전트
├── 🎯 preference_based_recommendation.py  # 2번: 취향 키워드 기반 추천 에이전트
├── 📝 review_summary_agent.py          # 3번: 리뷰 장단점 요약 에이전트
├── 🤖 취향기반추천.py                  # 4번: 인터랙티브 취향 선택 + GPT-4o 관련성 점수
├── 📦 requirements.txt
├── 🔧 .env.example                     # API 키 예시 (선택)
└── 📖 README.md
```

---

## 📖 사용 예시

<details>
<summary><b>🥇 1번 — 제품 비교</b></summary>

<br>

```
나이키 에어 포스 1 07 W - 화이트와 푸마 터프패디드 FS 코듀로이
A 코트 vs B 코트
```
</details>

<details>
<summary><b>🎯 2번 — 취향 키워드 추천</b></summary>

<br>

```
미니멀리즘, 30만원대, 아르켓 느낌
스트릿 스타일, 20만원, 나이키
```
</details>

<details>
<summary><b>📝 3번 — 리뷰 요약</b></summary>

<br>

```
나이키 에어맥스
무신사 코트
```
</details>

<details>
<summary><b>🤖 4번 — 인터랙티브 추천</b></summary>

<br>

- 카테고리(상의 / 하의 / 아우터 등) → 스타일(미니멀 / 캠퍼스 / 스트릿 등) → 브랜드·가격대 선택
- 필요 시 자연어로 추가 설명 입력 가능
</details>

---

## 🔧 기술 스택

<div align="center">

| 기술 | 역할 |
|------|------|
| 🔍 **Tavily API** | 웹 검색 (무신사 도메인 우선) |
| 🧠 **OpenAI API** *(선택)* | 4번 메뉴에서 관련성 점수·추천 이유 생성 |
| ⚙️ **python-dotenv** | `.env`에서 API 키 로드 (없으면 루트 `.env` 직접 읽기) |

</div>

---
