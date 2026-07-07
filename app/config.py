"""애플리케이션 설정.

pydantic-settings 기반으로 환경변수와 .env 파일에서 설정을 읽는다.
API 키는 임포트 시점에 강제하지 않고, 실제 외부 클라이언트를 만드는 시점에 검증한다.
(키 없이도 테스트/CLI 도움말 등이 동작해야 하므로)
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # 외부 API 키
    tavily_api_key: str | None = None
    openai_api_key: str | None = None

    # 검색 결과 캐시 (TTL + LRU)
    cache_ttl_seconds: float = 300.0
    cache_max_size: int = 256

    # 토큰 버킷 rate limiter
    rate_limit_per_second: float = 5.0
    rate_limit_burst: int = 10

    # 서킷 브레이커
    circuit_failure_threshold: int = 5
    circuit_recovery_timeout: float = 30.0

    # 재시도 (지수 백오프)
    retry_max_attempts: int = 3
    retry_base_delay: float = 0.5
    retry_max_delay: float = 8.0

    # Tavily 검색 파라미터
    search_max_workers: int = 4
    search_max_results: int = 5
    search_depth: str = "advanced"

    # LLM (추천 이유 생성)
    openai_model: str = "gpt-4o"


@lru_cache
def get_settings() -> Settings:
    """설정 싱글턴. 프로세스당 한 번만 파싱한다."""
    return Settings()
