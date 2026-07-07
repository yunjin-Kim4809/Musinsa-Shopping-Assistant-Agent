# 무신사 쇼핑 도움 에이전트 API 서버
#
# 빌드:  docker build -t musinsa-agent .
# 실행:  docker run -p 8000:8000 --env-file .env musinsa-agent

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# 의존성 레이어 분리: 코드만 바뀌면 pip install 레이어는 캐시 재사용
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/
COPY main.py ./

# 비루트 사용자로 실행 (컨테이너 보안 기본 수칙)
RUN useradd --create-home appuser
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health')" || exit 1

CMD ["uvicorn", "app.api.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
