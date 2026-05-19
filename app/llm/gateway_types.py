from typing import Any

from pydantic import BaseModel, Field


class LLMGatewayResponse(BaseModel):
    prompt_id: str
    provider: str
    model: str
    output: str
    cached: bool = False
    latency_ms: int | None = None
    usage: dict[str, Any] = Field(default_factory=dict)
