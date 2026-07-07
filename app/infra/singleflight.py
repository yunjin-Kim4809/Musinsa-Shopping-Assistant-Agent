"""Singleflight: 동일 키의 동시 호출 병합.

캐시 미스 순간에 같은 키의 요청이 N개 동시에 들어오면, 캐시만으로는
N번의 원격 호출이 모두 나간다 (cache stampede). Singleflight 는 같은 키의
동시 호출 중 **첫 번째(리더)만 실제 실행**하고, 나머지(팔로워)는 리더의
결과를 공유받게 한다. (Go 표준 확장 golang.org/x/sync/singleflight 패턴)

캐시와의 역할 분담
------------------
- 캐시: "시간축" 중복 제거 — 이미 끝난 호출의 결과 재사용 (TTL 동안)
- singleflight: "동시성축" 중복 제거 — 지금 진행 중인 호출에 합류

구현 포인트
-----------
- 리더 선출은 락 안에서 dict 등록으로 원자적으로 결정한다.
- 리더의 예외도 팔로워 전원에게 그대로 전파한다 (성공만 공유하면
  팔로워들이 일제히 재호출해 stampede 가 재발한다).
- 완료 즉시 in-flight 테이블에서 제거 → 다음 호출은 새 flight 를 연다.
  (결과 보존은 캐시의 몫이므로 여기서는 들고 있지 않는다)
"""

from __future__ import annotations

import threading
from collections.abc import Callable, Hashable
from typing import Any, TypeVar

T = TypeVar("T")


class _Call:
    """진행 중인 호출 1건. 리더가 결과/예외를 채우고 event 로 팔로워를 깨운다."""

    __slots__ = ("event", "result", "exception")

    def __init__(self):
        self.event = threading.Event()
        self.result: Any = None
        self.exception: BaseException | None = None


class SingleFlight:
    """키별로 동시 호출을 1회 실행으로 병합하는 실행기."""

    def __init__(self):
        self._lock = threading.Lock()
        self._in_flight: dict[Hashable, _Call] = {}

    def do(self, key: Hashable, fn: Callable[[], T]) -> T:
        """key 에 대한 fn 실행. 이미 같은 key 가 실행 중이면 그 결과를 기다려 공유한다."""
        with self._lock:
            call = self._in_flight.get(key)
            if call is None:
                call = _Call()
                self._in_flight[key] = call
                is_leader = True
            else:
                is_leader = False

        if not is_leader:
            call.event.wait()
            if call.exception is not None:
                raise call.exception
            return call.result

        try:
            call.result = fn()
        except BaseException as exc:
            call.exception = exc
            raise
        finally:
            with self._lock:
                self._in_flight.pop(key, None)
            call.event.set()
        return call.result

    def in_flight_count(self) -> int:
        with self._lock:
            return len(self._in_flight)
