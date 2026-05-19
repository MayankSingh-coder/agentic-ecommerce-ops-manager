from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field


class PromptConfig(BaseModel):
    prompt_id: str
    agent: str
    provider: str
    model: str
    system_prompt: str = ""
    temperature: float = Field(ge=0)
    max_tokens: int = Field(gt=0)
    input_schema: str
    output_schema: str
    allowed_for_agents: list[str]
    fallback: dict[str, Any] | None = None
    cache_policy: dict[str, Any] = Field(default_factory=dict)


class PromptRegistry:
    def __init__(self, prompt_dir: str | Path = "prompts") -> None:
        if prompt_dir == "prompts":
            self.prompt_dir = Path(__file__).resolve().parents[2] / "prompts"
        else:
            self.prompt_dir = Path(prompt_dir)
        self._prompts = self._load_prompts()

    def get(self, prompt_id: str) -> PromptConfig:
        prompt = self._prompts.get(prompt_id)
        if prompt is None:
            raise KeyError(f"Prompt not found: {prompt_id}")
        return prompt

    def list_prompt_ids(self) -> list[str]:
        return sorted(self._prompts)

    def _load_prompts(self) -> dict[str, PromptConfig]:
        prompts: dict[str, PromptConfig] = {}
        for path in sorted(self.prompt_dir.glob("*.yaml")):
            with path.open("r", encoding="utf-8") as prompt_file:
                data = yaml.safe_load(prompt_file)
            prompt = PromptConfig(**data)
            prompts[prompt.prompt_id] = prompt
        return prompts
