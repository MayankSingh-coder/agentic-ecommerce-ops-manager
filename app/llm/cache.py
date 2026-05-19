import time
from dataclasses import dataclass

from app.llm.gateway_types import LLMGatewayResponse


@dataclass
class CacheEntry:
    response: LLMGatewayResponse
    expires_at: float | None


class InMemoryLLMCache:
    def __init__(self) -> None:
        self._store: dict[str, CacheEntry] = {}

    def get(self, key: str) -> LLMGatewayResponse | None:
        entry = self._store.get(key)
        if entry is None:
            return None
        if entry.expires_at is not None and entry.expires_at <= time.time():
            self._store.pop(key, None)
            return None
        return entry.response.model_copy(update={"cached": True})

    def set(self, key: str, response: LLMGatewayResponse, ttl_seconds: int | None = None) -> None:
        expires_at = None
        if ttl_seconds is not None:
            expires_at = time.time() + ttl_seconds
        self._store[key] = CacheEntry(
            response=response.model_copy(update={"cached": False}),
            expires_at=expires_at,
        )

    def clear(self) -> None:
        self._store.clear()
