from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.ecommerce_ops.agents.customer_insight_agent import CustomerInsightAgent
from app.ecommerce_ops.agents.inventory_agent import InventoryAgent
from app.ecommerce_ops.agents.marketing_agent import MarketingAgent
from app.ecommerce_ops.contracts import (
    AgentContext,
    AgentName,
    CustomerInsightAgentInput,
    InventoryAgentInput,
    MarketingAgentInput,
    MarketingChannel,
    RiskLevel,
)
from app.ecommerce_ops.repository import EcommerceOpsRepository
from tests.test_api.helpers import create_test_app


def create_marketing_input() -> MarketingAgentInput:
    repository = EcommerceOpsRepository()
    context = AgentContext(
        run_id="marketing-test-run",
        prompt_version="marketing_agent_rules_v1",
        created_at=datetime.now(timezone.utc),
    )
    inventory_recommendations, _ = InventoryAgent().run(
        InventoryAgentInput(
            context=context,
            products=repository.list_products(),
            inventory=repository.list_inventory(),
            orders=repository.list_orders(),
            lookback_days=30,
        )
    )
    customer_insights, _ = CustomerInsightAgent().run(
        CustomerInsightAgentInput(
            context=context,
            products=repository.list_products(),
            reviews=repository.list_reviews(),
            returns=repository.list_returns(),
            lookback_days=30,
        )
    )
    return MarketingAgentInput(
        context=context,
        products=repository.list_products(),
        inventory_recommendations=inventory_recommendations,
        customer_insights=customer_insights,
        channels=[MarketingChannel.email],
    )


def test_marketing_agent_blocks_campaigns_for_stock_or_quality_risk():
    drafts, run_record = MarketingAgent().run(create_marketing_input())

    assert run_record.agent_name == AgentName.marketing
    blocked_drafts = [draft for draft in drafts if draft.blocked_reason]
    assert len(blocked_drafts) == 2
    assert {draft.target_skus[0] for draft in blocked_drafts} == {"SKU-1001", "SKU-1002"}
    assert all(draft.risk_level == RiskLevel.high for draft in blocked_drafts)


def test_marketing_agent_creates_sendable_draft_for_safe_product():
    drafts, _ = MarketingAgent().run(create_marketing_input())

    draft = next(item for item in drafts if item.target_skus == ["SKU-1003"])

    assert draft.blocked_reason is None
    assert draft.requires_approval is True
    assert draft.offer == "10% off"
    assert draft.subject_lines
    assert "requires approval before send" in draft.body


def test_marketing_agent_api_persists_drafts_and_creates_send_approval():
    client = TestClient(create_test_app())

    response = client.post(
        "/api/v1/ecommerce-ops/agents/marketing/run",
        json={"run_id": "marketing-api-test", "channels": ["email"]},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["run"]["run_id"] == "marketing-api-test"
    assert payload["run"]["agent_name"] == "marketing"
    assert len(payload["drafts"]) == 3

    approvals = client.get("/api/v1/ecommerce-ops/approvals").json()
    marketing_approvals = [
        approval
        for approval in approvals
        if approval["agent_name"] == "marketing"
    ]
    assert len(marketing_approvals) == 1
    assert marketing_approvals[0]["resource_type"] == "marketing_draft"
    assert marketing_approvals[0]["resource_id"] == "SKU-1003"
    assert marketing_approvals[0]["status"] == "pending"
