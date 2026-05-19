import hashlib
import json
import time
from typing import Any

import httpx

from app.config import settings
from app.llm.cache import InMemoryLLMCache
from app.llm.gateway_types import LLMGatewayResponse
from app.llm.prompt_registry import PromptConfig, PromptRegistry


class LLMGateway:
    def __init__(
        self,
        prompt_registry: PromptRegistry | None = None,
        http_client: httpx.Client | None = None,
        provider_override: str | None = None,
        cache: InMemoryLLMCache | None = None,
    ) -> None:
        self.prompt_registry = prompt_registry or PromptRegistry()
        self.http_client = http_client
        self.provider_override = provider_override or settings.llm_gateway_provider
        self.cache = cache or InMemoryLLMCache()

    def generate_text(self, prompt_id: str, agent: str, input_data: dict[str, Any]) -> LLMGatewayResponse:
        prompt = self.prompt_registry.get(prompt_id)
        self._validate_agent_permission(prompt, agent)
        provider = self._resolve_provider(prompt)
        cache_key = self._cache_key(prompt=prompt, provider=provider, agent=agent, input_data=input_data)
        if self._cache_enabled(prompt):
            cached_response = self.cache.get(cache_key)
            if cached_response is not None:
                return cached_response

        response = self._generate_uncached(prompt=prompt, provider=provider, input_data=input_data)
        if self._cache_enabled(prompt):
            self.cache.set(cache_key, response, ttl_seconds=self._cache_ttl_seconds(prompt))
        return response

    def _validate_agent_permission(self, prompt: PromptConfig, agent: str) -> None:
        if agent not in prompt.allowed_for_agents:
            raise PermissionError(f"Agent {agent} cannot use prompt {prompt.prompt_id}")

    def _resolve_provider(self, prompt: PromptConfig) -> str:
        if self.provider_override == "prompt":
            return prompt.provider
        return self.provider_override

    def _generate_uncached(
        self,
        prompt: PromptConfig,
        provider: str,
        input_data: dict[str, Any],
    ) -> LLMGatewayResponse:
        if provider == "litellm":
            try:
                return self._litellm_completion(prompt, input_data)
            except httpx.HTTPError as exc:
                return self._fallback_completion(prompt, input_data, exc)
        return LLMGatewayResponse(
            prompt_id=prompt.prompt_id,
            provider=provider,
            model=prompt.model,
            output=self._stub_output(prompt, input_data),
            cached=False,
        )

    def _cache_enabled(self, prompt: PromptConfig) -> bool:
        return bool(prompt.cache_policy.get("enabled", False))

    def _cache_ttl_seconds(self, prompt: PromptConfig) -> int | None:
        ttl_seconds = prompt.cache_policy.get("ttl_seconds")
        if ttl_seconds is None:
            return None
        return int(ttl_seconds)

    def _cache_key(
        self,
        prompt: PromptConfig,
        provider: str,
        agent: str,
        input_data: dict[str, Any],
    ) -> str:
        payload = json.dumps(
            {
                "prompt_id": prompt.prompt_id,
                "provider": provider,
                "model": prompt.model,
                "temperature": prompt.temperature,
                "max_tokens": prompt.max_tokens,
                "agent": agent,
                "input": input_data,
            },
            default=str,
            sort_keys=True,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def _litellm_completion(self, prompt: PromptConfig, input_data: dict[str, Any]) -> LLMGatewayResponse:
        started_at = time.perf_counter()
        client = self.http_client or httpx.Client(timeout=settings.litellm_timeout_seconds)
        headers = {"Content-Type": "application/json"}
        if settings.litellm_api_key:
            headers["Authorization"] = f"Bearer {settings.litellm_api_key}"

        response = client.post(
            f"{settings.litellm_base_url.rstrip('/')}/v1/chat/completions",
            headers=headers,
            json={
                "model": prompt.model,
                "messages": [
                    {
                        "role": "system",
                        "content": prompt.system_prompt or f"You are running prompt {prompt.prompt_id}.",
                    },
                    {
                        "role": "user",
                        "content": json.dumps(input_data, default=str, sort_keys=True),
                    },
                ],
                "temperature": prompt.temperature,
                "max_tokens": prompt.max_tokens,
            },
        )
        response.raise_for_status()
        payload = response.json()
        output = payload["choices"][0]["message"]["content"]
        return LLMGatewayResponse(
            prompt_id=prompt.prompt_id,
            provider="litellm",
            model=prompt.model,
            output=output,
            cached=False,
            latency_ms=int((time.perf_counter() - started_at) * 1000),
            usage=payload.get("usage", {}),
        )

    def _fallback_completion(
        self,
        prompt: PromptConfig,
        input_data: dict[str, Any],
        error: Exception,
    ) -> LLMGatewayResponse:
        return LLMGatewayResponse(
            prompt_id=prompt.prompt_id,
            provider="stub",
            model=prompt.model,
            output=self._stub_output(prompt, input_data),
            cached=False,
            usage={
                "fallback_reason": error.__class__.__name__,
                "fallback_provider": "litellm",
            },
        )

    def _stub_output(self, prompt: PromptConfig, input_data: dict[str, Any]) -> str:
        if prompt.prompt_id == "daily_ops_summary_v1":
            return self._daily_ops_summary(input_data)
        if prompt.prompt_id == "marketing_draft_v1":
            return self._marketing_body(input_data)
        if prompt.prompt_id == "customer_insight_clustering_v1":
            return self._customer_insight_clusters(input_data)
        return "LLM gateway stub output."

    def _daily_ops_summary(self, input_data: dict[str, Any]) -> str:
        inventory_count = len(input_data.get("inventory_alerts", []))
        pricing_count = len(input_data.get("pricing_recommendations", []))
        marketing_count = len(input_data.get("marketing_drafts", []))
        approval_count = len(input_data.get("approvals_required", []))
        blocked_count = len(input_data.get("actions_blocked", []))
        return (
            f"Daily ops completed with {inventory_count} inventory alerts, "
            f"{pricing_count} pricing recommendations, {marketing_count} marketing drafts, "
            f"{blocked_count} blocked actions, and {approval_count} pending approvals."
        )

    def _marketing_body(self, input_data: dict[str, Any]) -> str:
        product_name = input_data.get("product_name", "this product")
        offer = input_data.get("offer", "a limited-time offer")
        return (
            f"Draft campaign for {product_name}: highlight the product value, "
            f"include {offer}, and requires approval before send."
        )

    def _customer_insight_clusters(self, input_data: dict[str, Any]) -> str:
        review_counts: dict[tuple[str, str], int] = {}
        return_counts: dict[tuple[str, str], int] = {}
        evidence: dict[tuple[str, str], list[str]] = {}

        for review in input_data.get("reviews", []):
            issue = self._semantic_issue_label(
                f"{review.get('title', '')} {review.get('body', '')}",
                fallback="Low rating" if review.get("rating", 5) <= 2 else None,
            )
            if issue is None:
                continue
            key = (review["sku"], issue)
            review_counts[key] = review_counts.get(key, 0) + 1
            evidence.setdefault(key, []).append(f"Review {review['review_id']}: {review.get('title', '')}")

        for product_return in input_data.get("returns", []):
            issue = self._return_issue_label(product_return)
            key = (product_return["sku"], issue)
            return_counts[key] = return_counts.get(key, 0) + 1
            if product_return.get("notes"):
                evidence.setdefault(key, []).append(
                    f"Return {product_return['return_id']}: {product_return['notes']}"
                )

        clusters = []
        for sku, issue in sorted(set(review_counts) | set(return_counts)):
            review_count = review_counts.get((sku, issue), 0)
            return_count = return_counts.get((sku, issue), 0)
            clusters.append(
                {
                    "sku": sku,
                    "issue": issue,
                    "review_count": review_count,
                    "return_count": return_count,
                    "representative_evidence": evidence.get((sku, issue), [])[:3],
                    "severity": self._issue_severity(review_count, return_count),
                }
            )

        if not clusters:
            summary = "No material product issues detected from reviews or returns."
        else:
            high_priority_skus = [
                cluster["sku"]
                for cluster in clusters
                if cluster["severity"] in {"high", "critical"}
            ]
            summary = (
                f"High-priority product issues detected for {', '.join(high_priority_skus)}."
                if high_priority_skus
                else "Product issues detected, but current evidence is low severity."
            )
        return json.dumps({"clusters": clusters, "summary": summary})

    def _semantic_issue_label(self, text: str, fallback: str | None = None) -> str | None:
        normalized = text.lower()
        if any(term in normalized for term in ["size", "sizing", "exchange", "bigger", "small", "tight", "loose"]):
            return "Size mismatch"
        if any(
            term in normalized
            for term in ["battery", "drain", "last", "charge", "power", "dies", "dead quickly", "doesn't hold"]
        ):
            return "Battery drain"
        if any(term in normalized for term in ["damaged", "broken", "packaging", "crushed", "box torn"]):
            return "Damaged packaging"
        return fallback

    def _return_issue_label(self, product_return: dict[str, Any]) -> str:
        reason = product_return.get("reason")
        notes = product_return.get("notes", "")
        semantic_issue = self._semantic_issue_label(notes)
        if semantic_issue is not None:
            return semantic_issue
        if reason == "size_mismatch":
            return "Size mismatch"
        if reason == "quality_issue":
            return "Quality issue"
        if reason == "damaged":
            return "Damaged packaging"
        if reason == "late_delivery":
            return "Late delivery"
        return "Other return reason"

    def _issue_severity(self, review_count: int, return_count: int) -> str:
        weighted_score = review_count + (return_count * 2)
        if weighted_score >= 8:
            return "critical"
        if weighted_score >= 3:
            return "high"
        if weighted_score >= 2:
            return "medium"
        return "low"
