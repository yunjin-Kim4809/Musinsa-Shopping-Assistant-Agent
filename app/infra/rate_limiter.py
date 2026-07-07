"""토큰 버킷(Token Bucket) rate limiter.

외부 검색 API 의 호출량 제한(쿼터/과금)을 클라이언트 쪽에서 선제적으로 지키기 위한 장치.

알고리즘
--------
- 버킷은 최대 capacity 개의 토큰을 담는다.
- 토큰은 초당 rate 개씩 채워진다.
- 요청은 토큰을 1개(이상) 소비해야 통과한다. 토큰이 없으면 대기하거나 거절.

고정 윈도우 카운터와 달리 경계 폭주(boundary burst) 문제가 없고,
버킷에 쌓인 토큰만큼의 순간 버스트(burst)는 허용하면서 장기 평균 속도를 rate 로 묶는다.

구현 포인트
-----------
- 토큰을 백그라운드 스레드로 채우지 않고, 접근 시점에 경과 시간으로 환산해
  한 번에 채우는 lazy refill 방식. 스레드가 없어 가볍고 정확하다.
- time.monotonic 사용: 벽시계(time.time)와 달리 시스템 시간 변경에 영향받지 않는다.
- 부족한 토큰이 채워질 시각을 계산해 그만큼만 sleep 하므로 busy-wait 이 없다.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable


class TokenBucket:
    """스레드 안전 토큰 버킷.

    Args:
        rate: 초당 리필되는 토큰 수.
        capacity: 버킷 최대 용량(=허용 버스트 크기).
        clock: 시간 함수(테스트용 주입 지점).
        sleep: 대기 함수(테스트용 주입 지점).
    """

    def __init__(
        self,
        rate: float,
        capacity: float,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ):
        if rate <= 0 or capacity <= 0:
            raise ValueError("rate와 capacity는 0보다 커야 합니다.")

        self._rate = rate
        self._capacity = capacity
        self._tokens = capacity  # 시작 시 가득 채워 초기 버스트 허용
        self._clock = clock
        self._sleep = sleep
        self._last_refill = clock()
        self._lock = threading.Lock()

    def _refill(self) -> None:
        """마지막 리필 이후 경과 시간만큼 토큰을 채운다. (락 보유 상태에서 호출)"""
        now = self._clock()
        elapsed = now - self._last_refill
        if elapsed > 0:
            self._tokens = min(self._capacity, self._tokens + elapsed * self._rate)
            self._last_refill = now

    def try_acquire(self, tokens: float = 1.0) -> bool:
        """토큰이 있으면 즉시 소비하고 True, 없으면 대기 없이 False."""
        with self._lock:
            self._refill()
            if self._tokens >= tokens:
                self._tokens -= tokens
                return True
            return False

    def acquire(self, tokens: float = 1.0, timeout: float | None = None) -> bool:
        """토큰을 확보할 때까지 대기. timeout 초과 시 False.

        부족분이 채워지는 데 걸리는 시간을 계산해 정확히 그만큼만 잔다.
        """
        if tokens > self._capacity:
            raise ValueError("요청 토큰 수가 버킷 용량을 초과합니다.")

        deadline = None if timeout is None else self._clock() + timeout

        while True:
            with self._lock:
                self._refill()
                if self._tokens >= tokens:
                    self._tokens -= tokens
                    return True
                # 부족한 토큰이 채워질 때까지 필요한 시간
                wait = (tokens - self._tokens) / self._rate

            if deadline is not None:
                remaining = deadline - self._clock()
                if remaining <= 0:
                    return False
                wait = min(wait, remaining)

            self._sleep(wait)

    @property
    def available_tokens(self) -> float:
        with self._lock:
            self._refill()
            return self._tokens
