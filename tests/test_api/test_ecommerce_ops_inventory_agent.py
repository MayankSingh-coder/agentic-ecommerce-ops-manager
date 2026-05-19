from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.ecommerce_ops.agents.inventory_agent import InventoryAgent
from app.ecommerce_ops.contracts import (
    AgentContext,
    AgentName,
    AgentRunStatus,
    InventoryAgentInput,
    RiskLevel,
)
from app.ecommerce_ops.repository import EcommerceOpsRepository
from tests.test_api.helpers import create_test_app


def create_inventory_input(lookback_days: int = 30) -> InventoryAgentInput:
    repository = EcommerceOpsRepository()
    return InventoryAgentInput(
        context=AgentContext(
            run_id="inventory-test-run",
            prompt_version="inventory_agent_rules_v1",
            created_at=datetime.now(timezone.utc),
        ),
        products=repository.list_products(),
        inventory=repository.list_inventory(),
        orders=repository.list_orders(),
        lookback_days=lookback_days,
    )


def test_inventory_agent_generates_recommendations_for_all_inventory_items():
    payload = create_inventory_input()
    recommendations, run_record = InventoryAgent().run(payload)

    assert run_record.run_id == "inventory-test-run"
    assert run_record.agent_name == AgentName.inventory
    assert run_record.status == AgentRunStatus.succeeded
    assert len(recommendations) == 3


def test_inventory_agent_flags_reorder_when_available_stock_hits_reorder_point():
    payload = create_inventory_input()
    recommendations, _ = InventoryAgent().run(payload)

    recommendation = next(item for item in recommendations if item.sku == "SKU-1001")

    assert recommendation.reorder_needed is True
    assert recommendation.risk_level == RiskLevel.medium
    assert recommendation.recommended_reorder_qty == 35
    assert "projected stock after lead time" in recommendation.reason


def test_inventory_agent_flags_high_risk_when_projected_stock_breaches_safety_stock():
    payload = create_inventory_input()
    recommendations, _ = InventoryAgent().run(payload)

    recommendation = next(item for item in recommendations if item.sku == "SKU-1002")

    assert recommendation.reorder_needed is True
    assert recommendation.risk_level == RiskLevel.high
    assert recommendation.recommended_reorder_qty == 35


def test_inventory_agent_leaves_healthy_stock_without_reorder():
    payload = create_inventory_input()
    recommendations, _ = InventoryAgent().run(payload)

    recommendation = next(item for item in recommendations if item.sku == "SKU-1003")

    assert recommendation.reorder_needed is False
    assert recommendation.risk_level == RiskLevel.low
    assert recommendation.recommended_reorder_qty == 0
    assert recommendation.days_of_inventory is None


def test_inventory_agent_api_returns_typed_run_response():
    client = TestClient(create_test_app())

    response = client.post(
        "/api/v1/ecommerce-ops/agents/inventory/run",
        json={"run_id": "inventory-api-test", "lookback_days": 30},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["run"]["run_id"] == "inventory-api-test"
    assert payload["run"]["agent_name"] == "inventory"
    assert payload["run"]["status"] == "succeeded"
    assert len(payload["recommendations"]) == 3
    assert payload["recommendations"][1]["sku"] == "SKU-1002"
    assert payload["recommendations"][1]["risk_level"] == "high"
