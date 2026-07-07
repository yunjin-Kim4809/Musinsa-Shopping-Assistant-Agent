"""TTL + LRU 캐시.

동일한 검색어가 반복될 때 외부 API 호출(수백 ms + 과금)을 줄이기 위한 인메모리 캐시.

자료구조
--------
- 해시맵: key -> 노드 참조. 조회 O(1)
- 이중 연결 리스트(센티널 노드 2개): 최근 사용 순서 유지.
  head 쪽이 최신(MRU), tail 쪽이 오래된 항목(LRU). 노드 이동/제거 O(1)

즉 get/put/evict 모두 O(1). functools.lru_cache 나 OrderedDict 로도 가능하지만,
TTL(항목별 만료)과 적중률 통계를 함께 다루기 위해 직접 구현했다.

만료 정책
---------
lazy expiration: 별도 타이머 스레드 없이, get 시점에 만료 여부를 검사해 제거한다.
용량 초과 시에는 tail(LRU) 항목부터 즉시 축출(eviction)한다.

스레드 안전성
-------------
FastAPI 스레드풀/병렬 검색에서 동시 접근하므로 RLock 으로 보호한다.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Hashable
from dataclasses import dataclass
from typing import Any


@dataclass
class CacheStats:
    hits: int = 0
    misses: int = 0
    evictions: int = 0
    expirations: int = 0

    @property
    def hit_rate(self) -> float:
        total = self.hits + self.misses
        return self.hits / total if total else 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "hits": self.hits,
            "misses": self.misses,
            "evictions": self.evictions,
            "expirations": self.expirations,
            "hit_rate": round(self.hit_rate, 4),
        }


class _Node:
    """이중 연결 리스트 노드. 메모리 절약을 위해 __slots__ 사용."""

    __slots__ = ("key", "value", "expires_at", "prev", "next")

    def __init__(self, key: Hashable, value: Any, expires_at: float):
        self.key = key
        self.value = value
        self.expires_at = expires_at
        self.prev: _Node | None = None
        self.next: _Node | None = None


class TTLLRUCache:
    """O(1) get/put 을 보장하는 TTL + LRU 캐시.

    Args:
        max_size: 최대 엔트리 수. 초과 시 LRU 항목부터 축출.
        ttl: 엔트리 생존 시간(초).
        clock: 시간 함수(기본 time.monotonic). 테스트에서 가짜 시계 주입용.
    """

    def __init__(
        self,
        max_size: int = 256,
        ttl: float = 300.0,
        clock: Callable[[], float] = time.monotonic,
    ):
        if max_size <= 0:
            raise ValueError("max_size는 1 이상이어야 합니다.")
        if ttl <= 0:
            raise ValueError("ttl은 0보다 커야 합니다.")

        self._max_size = max_size
        self._ttl = ttl
        self._clock = clock
        self._map: dict[Hashable, _Node] = {}
        self._lock = threading.RLock()
        self.stats = CacheStats()

        # 센티널 노드: 경계 조건(빈 리스트, 첫/마지막 노드) 분기를 없앤다.
        self._head = _Node(None, None, 0.0)  # head.next == MRU
        self._tail = _Node(None, None, 0.0)  # tail.prev == LRU
        self._head.next = self._tail
        self._tail.prev = self._head

    # --- 이중 연결 리스트 조작 (모두 O(1)) ---

    def _unlink(self, node: _Node) -> None:
        node.prev.next = node.next
        node.next.prev = node.prev

    def _push_front(self, node: _Node) -> None:
        node.next = self._head.next
        node.prev = self._head
        self._head.next.prev = node
        self._head.next = node

    def _move_to_front(self, node: _Node) -> None:
        self._unlink(node)
        self._push_front(node)

    # --- 공개 API ---

    def get(self, key: Hashable, default: Any = None) -> Any:
        with self._lock:
            node = self._map.get(key)
            if node is None:
                self.stats.misses += 1
                return default

            if node.expires_at <= self._clock():
                # lazy expiration: 접근 시점에 만료된 항목 제거
                self._unlink(node)
                del self._map[key]
                self.stats.expirations += 1
                self.stats.misses += 1
                return default

            self._move_to_front(node)
            self.stats.hits += 1
            return node.value

    def put(self, key: Hashable, value: Any) -> None:
        with self._lock:
            expires_at = self._clock() + self._ttl
            node = self._map.get(key)

            if node is not None:
                node.value = value
                node.expires_at = expires_at
                self._move_to_front(node)
                return

            node = _Node(key, value, expires_at)
            self._map[key] = node
            self._push_front(node)

            if len(self._map) > self._max_size:
                lru = self._tail.prev
                self._unlink(lru)
                del self._map[lru.key]
                self.stats.evictions += 1

    def get_or_set(self, key: Hashable, factory: Callable[[], Any]) -> Any:
        """캐시에 있으면 반환, 없으면 factory 실행 후 저장.

        주의: factory 실행은 락 밖에서 수행한다. 외부 API 호출(수백 ms)이
        락을 쥐고 있으면 다른 스레드의 캐시 접근이 전부 직렬화되기 때문.
        같은 키에 대한 중복 호출(cache stampede)은 감수하는 트레이드오프.
        """
        sentinel = object()
        value = self.get(key, sentinel)
        if value is not sentinel:
            return value
        value = factory()
        self.put(key, value)
        return value

    def clear(self) -> None:
        with self._lock:
            self._map.clear()
            self._head.next = self._tail
            self._tail.prev = self._head

    def __contains__(self, key: Hashable) -> bool:
        sentinel = object()
        return self.get(key, sentinel) is not sentinel

    def __len__(self) -> int:
        with self._lock:
            return len(self._map)
