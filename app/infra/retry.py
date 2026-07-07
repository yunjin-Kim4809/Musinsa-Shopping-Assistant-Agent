"""지수 백오프(exponential backoff) + full jitter 재시도.

일시적 네트워크 오류/타임아웃은 잠시 후 재시도하면 성공하는 경우가 많다.
단, 고정 간격으로 일제히 재시도하면 장애 서버에 요청이 몰리는
thundering herd 문제가 생기므로:

- 지수 백오프: 시도마다 대기 상한을 2배씩 늘린다 (base * 2^attempt).
- full jitter: 실제 대기는 [0, 상한) 균등 난수로 뽑아 재시도 시점을 분산시킨다.
  (AWS Architecture Blog "Exponential Backoff and Jitter" 의 권장 방식)

서킷 브레이커와의 조합
----------------------
CircuitOpenError 는 "서버가 죽어 있으니 부르지 말라"는 신호이므로
재시도해봐야 의미가 없다 → non_retryable 로 기본 등록해 즉시 전파한다.
"""

from __future__ import annotations

import functools
import logging
import random
import time
from collections.abc import Callable
from typing import Any, TypeVar

from app.infra.circuit_breaker import CircuitOpenError

logger = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable[..., Any])


def compute_backoff(
    attempt: int,
    base_delay: float,
    max_delay: float,
    rng: Callable[[], float] = random.random,
) -> float:
    """attempt(0부터 시작)번째 실패 후 대기 시간을 계산한다.

    delay = U(0, min(max_delay, base_delay * 2^attempt))
    """
    cap = min(max_delay, base_delay * (2**attempt))
    return rng() * cap


def retry(
    max_attempts: int = 3,
    base_delay: float = 0.5,
    max_delay: float = 8.0,
    retryable: tuple[type[Exception], ...] = (Exception,),
    non_retryable: tuple[type[Exception], ...] = (CircuitOpenError,),
    sleep: Callable[[float], None] = time.sleep,
    rng: Callable[[], float] = random.random,
) -> Callable[[F], F]:
    """함수에 재시도 정책을 입히는 데코레이터.

    Args:
        max_attempts: 최초 시도 포함 총 시도 횟수.
        base_delay: 백오프 기본 단위(초).
        max_delay: 백오프 상한(초).
        retryable: 재시도 대상 예외.
        non_retryable: 재시도하지 않고 즉시 전파할 예외 (retryable보다 우선).
        sleep/rng: 테스트용 주입 지점.
    """
    if max_attempts < 1:
        raise ValueError("max_attempts는 1 이상이어야 합니다.")

    def decorator(fn: F) -> F:
        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            last_exc: Exception | None = None
            for attempt in range(max_attempts):
                try:
                    return fn(*args, **kwargs)
                except non_retryable:
                    raise
                except retryable as exc:
                    last_exc = exc
                    if attempt == max_attempts - 1:
                        break
                    delay = compute_backoff(attempt, base_delay, max_delay, rng)
                    logger.warning(
                        "%s 호출 실패(%s). %.2f초 후 재시도 (%d/%d)",
                        fn.__name__,
                        exc,
                        delay,
                        attempt + 2,
                        max_attempts,
                    )
                    sleep(delay)
            raise last_exc  # type: ignore[misc]

        return wrapper  # type: ignore[return-value]

    return decorator
