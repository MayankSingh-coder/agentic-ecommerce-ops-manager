from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.ecommerce_ops.agents.pricing_agent import PricingAgent
from app.ecommerce_ops.contracts import (
    AgentContext,
    AgentName,
    AgentRunStatus,
    PolicyDecision,
    PricingAgentInput,
    RiskLevel,
)
from app.ecommerce_ops.policies.pricing_policy import PricingPolicyEngine
from app.ecommerce_ops.repository import EcommerceOpsRepository
from tests.test_api.helpers import create_test_app


def create_pricing_input() -> PricingAgentInput:
    repository = EcommerceOpsRepository()
    return PricingAgentInput(
        context=AgentContext(
            run_id="pricing-test-run",
            prompt_version="pricing_agent_rules_v1",
            created_at=datetime(2026, 5, 18, 12, 0, tzinfo=timezone.utc),
        ),
        products=repository.list_products(),
        inventory=repository.list_inventory(),
        orders=repository.list_orders(),
        competitor_prices=repository.list_competitors(),
    )


def test_pricing_agent_generates_recommendations_for_products_with_competitor_data():
    recommendations, run_record = PricingAgent().run(create_pricing_input())

    assert run_record.run_id == "pricing-test-run"
    assert run_record.agent_name == AgentName.pricing
    assert run_record.status == AgentRunStatus.succeeded
    assert [recommendation.sku for recommendation in recommendations] == ["SKU-1001", "SKU-1002"]


def test_pricing_agent_allows_safe_competitor_match_when_policy_passes():
    recommendations, _ = PricingAgent().run(create_pricing_input())

    recommendation = next(item for item in recommendations if item.sku == "SKU-1001")

    assert recommendation.current_price == 1499
    assert recommendation.recommended_price == 1399
    assert recommendation.price_change_pct == -6.67
    assert recommendation.recommended_margin_pct == 34.95
    assert recommendation.policy_decision == PolicyDecision.allowed
    assert recommendation.requires_approval is False
    assert recommendation.risk_level == RiskLevel.low


def test_pricing_agent_blocks_discount_on_critical_stock_sku():
    recommendations, _ = PricingAgent().run(create_pricing_input())

    recommendation = next(item for item in recommendations if item.sku == "SKU-1002")

    assert recommendation.current_price == 2299
    assert recommendation.recommended_price == 2299
    assert recommendation.price_change_pct == 0
    assert recommendation.expected_revenue_impact == 0
    assert recommendation.policy_decision == PolicyDecision.blocked
    assert recommendation.requires_approval is False
    assert recommendation.risk_level == RiskLevel.high
    assert "critical-stock" in recommendation.reason


def test_pricing_policy_requires_approval_for_large_price_movement():
    result = PricingPolicyEngine().evaluate(
        current_price=1000,
        recommended_price=850,
        recommended_margin_pct=30,
        competitor_confidence=0.95,
        competitor_observed_at=datetime(2026, 5, 18, 10, 0, tzinfo=timezone.utc),
        inventory_item=None,
        expected_revenue_impact=-1500,
        reference_time=datetime(2026, 5, 18, 12, 0, tzinfo=timezone.utc),
    )

    assert result.decision == PolicyDecision.approval_required
    assert result.requires_approval is True
    assert result.risk_level == RiskLevel.high


def test_pricing_agent_api_returns_typed_run_response():
    client = TestClient(create_test_app())

    response = client.post(
        "/api/v1/ecommerce-ops/agents/pricing/run",
        json={"run_id": "pricing-api-test"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["run"]["run_id"] == "pricing-api-test"
    assert payload["run"]["agent_name"] == "pricing"
    assert payload["run"]["status"] == "succeeded"
    assert len(payload["recommendations"]) == 2
    assert payload["recommendations"][1]["sku"] == "SKU-1002"
    assert payload["recommendations"][1]["policy_decision"] == "blocked"
