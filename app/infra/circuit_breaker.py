"""서킷 브레이커(Circuit Breaker) 패턴.

외부 API(Tavily)가 장애 상태일 때, 실패할 것이 뻔한 호출을 계속 보내며
타임아웃을 기다리는 대신 즉시 실패시켜 장애 전파를 차단한다.

상태 머신
---------
::

            실패 threshold회 연속
    CLOSED ──────────────────────> OPEN
      ^                             │
      │ 프로브 성공                  │ recovery_timeout 경과
      │                             v
      └────────────────────── HALF_OPEN
                 │ 프로브 실패 시 다시 OPEN

- CLOSED   : 정상. 모든 호출 통과. 연속 실패 횟수를 센다.
- OPEN     : 차단. 호출 즉시 CircuitOpenError. 복구 대기 시간이 지나면 HALF_OPEN.
- HALF_OPEN: 반개방. 제한된 수의 프로브 호출만 통과시켜 복구 여부를 탐침한다.
             성공하면 CLOSED 복귀, 실패하면 다시 OPEN.

구현 포인트
-----------
- 상태 전이는 락으로 보호해 원자적으로 수행한다.
- HALF_OPEN 에서 동시에 여러 스레드가 프로브를 쏟아내지 않도록
  진행 중 프로브 수(half_open_max_calls)를 제한한다.
"""

from __future__ import annotations

import enum
import threading
import time
from collections.abc import Callable
from typing import Any, TypeVar

T = TypeVar("T")


class CircuitState(enum.Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitOpenError(Exception):
    """서킷이 OPEN 상태여서 호출이 차단됨."""

    def __init__(self, retry_after: float):
        self.retry_after = max(0.0, retry_after)
        super().__init__(
            f"서킷 브레이커가 열려 있습니다. 약 {self.retry_after:.1f}초 후 재시도 가능."
        )


class CircuitBreaker:
    """스레드 안전 서킷 브레이커.

    Args:
        failure_threshold: OPEN 으로 전이되는 연속 실패 횟수.
        recovery_timeout: OPEN 유지 시간(초). 경과 후 HALF_OPEN 프로브 허용.
        half_open_max_calls: HALF_OPEN 에서 동시에 허용할 프로브 호출 수.
        clock: 시간 함수(테스트용 주입 지점).
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
        half_open_max_calls: int = 1,
        clock: Callable[[], float] = time.monotonic,
    ):
        if failure_threshold < 1:
            raise ValueError("failure_threshold는 1 이상이어야 합니다.")

        self._failure_threshold = failure_threshold
        self._recovery_timeout = recovery_timeout
        self._half_open_max_calls = half_open_max_calls
        self._clock = clock

        self._state = CircuitState.CLOSED
        self._consecutive_failures = 0
        self._opened_at = 0.0
        self._half_open_in_flight = 0
        self._lock = threading.RLock()

    @property
    def state(self) -> CircuitState:
        with self._lock:
            self._maybe_transition_to_half_open()
            return self._state

    def _maybe_transition_to_half_open(self) -> None:
        """OPEN 상태에서 복구 대기 시간이 지났으면 HALF_OPEN 으로 전이."""
        if (
            self._state is CircuitState.OPEN
            and self._clock() - self._opened_at >= self._recovery_timeout
        ):
            self._state = CircuitState.HALF_OPEN
            self._half_open_in_flight = 0

    def _acquire_permit(self) -> None:
        """호출 허가를 얻는다. 불가하면 CircuitOpenError."""
        with self._lock:
            self._maybe_transition_to_half_open()

            if self._state is CircuitState.OPEN:
                retry_after = self._recovery_timeout - (self._clock() - self._opened_at)
                raise CircuitOpenError(retry_after)

            if self._state is CircuitState.HALF_OPEN:
                if self._half_open_in_flight >= self._half_open_max_calls:
                    # 이미 다른 스레드가 프로브 중 → 결과가 나올 때까지 차단
                    raise CircuitOpenError(0.0)
                self._half_open_in_flight += 1

    def record_success(self) -> None:
        with self._lock:
            if self._state is CircuitState.HALF_OPEN:
                self._half_open_in_flight = max(0, self._half_open_in_flight - 1)
                self._state = CircuitState.CLOSED
            self._consecutive_failures = 0

    def record_failure(self) -> None:
        with self._lock:
            if self._state is CircuitState.HALF_OPEN:
                # 프로브 실패 → 즉시 다시 OPEN
                self._half_open_in_flight = max(0, self._half_open_in_flight - 1)
                self._trip()
                return

            self._consecutive_failures += 1
            if self._consecutive_failures >= self._failure_threshold:
                self._trip()

    def _trip(self) -> None:
        self._state = CircuitState.OPEN
        self._opened_at = self._clock()
        self._consecutive_failures = 0

    def call(self, fn: Callable[..., T], *args: Any, **kwargs: Any) -> T:
        """fn 을 서킷 브레이커 보호 하에 실행한다."""
        self._acquire_permit()
        try:
            result = fn(*args, **kwargs)
        except Exception:
            self.record_failure()
            raise
        self.record_success()
        return result

    def snapshot(self) -> dict[str, Any]:
        """관측용 상태 스냅샷 (모니터링 엔드포인트에서 사용)."""
        with self._lock:
            self._maybe_transition_to_half_open()
            return {
                "state": self._state.value,
                "consecutive_failures": self._consecutive_failures,
                "failure_threshold": self._failure_threshold,
                "recovery_timeout": self._recovery_timeout,
            }
