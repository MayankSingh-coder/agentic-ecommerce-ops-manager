from datetime import datetime, timezone

from fastapi.testclient import TestClient

from tests.test_api.helpers import create_test_app


def test_review_mutation_changes_customer_insight_workflow_output():
    client = TestClient(create_test_app())

    response = client.post(
        "/api/v1/ecommerce-ops/reviews",
        json={
            "review_id": "REV-DEMO-BATTERY",
            "sku": "SKU-1003",
            "rating": 1,
            "title": "Power dies quickly",
            "body": "The backpack accessory battery does not hold charge.",
            "created_at": datetime.now(timezone.utc).isoformat(),
        },
    )

    assert response.status_code == 200
    assert response.json()["review_id"] == "REV-DEMO-BATTERY"

    insight_response = client.post(
        "/api/v1/ecommerce-ops/agents/customer-insights/run",
        json={"run_id": "mutation-insight-demo", "lookback_days": 30},
    )

    assert insight_response.status_code == 200
    clusters = insight_response.json()["report"]["clusters"]
    assert any(
        cluster["sku"] == "SKU-1003" and cluster["issue"] == "Battery drain"
        for cluster in clusters
    )


def test_inventory_mutation_changes_inventory_agent_output():
    client = TestClient(create_test_app())

    response = client.patch(
        "/api/v1/ecommerce-ops/inventory/SKU-1003",
        json={
            "warehouse": "DEL-02",
            "available_stock": 1,
            "reserved_stock": 1,
            "reorder_point": 35,
            "supplier_lead_time_days": 5,
            "safety_stock": 18,
            "status": "critical",
        },
    )

    assert response.status_code == 200
    assert response.json()["available_stock"] == 1

    inventory_response = client.post(
        "/api/v1/ecommerce-ops/agents/inventory/run",
        json={"run_id": "mutation-inventory-demo", "lookback_days": 30},
    )

    assert inventory_response.status_code == 200
    recommendation = next(
        item
        for item in inventory_response.json()["recommendations"]
        if item["sku"] == "SKU-1003"
    )
    assert recommendation["reorder_needed"] is True
    assert recommendation["risk_level"] == "critical"


def test_competitor_mutation_changes_pricing_reference():
    client = TestClient(create_test_app())

    response = client.post(
        "/api/v1/ecommerce-ops/competitors",
        json={
            "sku": "SKU-1003",
            "competitor": "BagOutlet",
            "price": 1799,
            "product_url": "https://example.com/bagoutlet/urbantrail-backpack",
            "observed_at": datetime.now(timezone.utc).isoformat(),
            "confidence": 0.96,
        },
    )

    assert response.status_code == 200

    pricing_response = client.post(
        "/api/v1/ecommerce-ops/agents/pricing/run",
        json={"run_id": "mutation-pricing-demo"},
    )

    assert pricing_response.status_code == 200
    recommendation = next(
        item
        for item in pricing_response.json()["recommendations"]
        if item["sku"] == "SKU-1003"
    )
    assert recommendation["competitor_reference_price"] == 1799


def test_return_mutation_is_available_to_workflow_inputs():
    client = TestClient(create_test_app())

    response = client.post(
        "/api/v1/ecommerce-ops/returns",
        json={
            "return_id": "RET-DEMO-SIZE",
            "order_id": "ORD-9001",
            "sku": "SKU-1001",
            "reason": "size_mismatch",
            "notes": "Second customer reports the shoe runs small.",
            "created_at": datetime.now(timezone.utc).isoformat(),
        },
    )

    assert response.status_code == 200
    returns_response = client.get("/api/v1/ecommerce-ops/returns")

    assert any(
        item["return_id"] == "RET-DEMO-SIZE"
        for item in returns_response.json()
    )


def test_mutation_api_rejects_unknown_sku():
    client = TestClient(create_test_app())

    response = client.post(
        "/api/v1/ecommerce-ops/reviews",
        json={
            "review_id": "REV-UNKNOWN",
            "sku": "SKU-NOT-FOUND",
            "rating": 1,
            "title": "Bad",
            "body": "Unknown product.",
            "created_at": datetime.now(timezone.utc).isoformat(),
        },
    )

    assert response.status_code == 404
    assert "Unknown product SKU" in response.json()["detail"]
