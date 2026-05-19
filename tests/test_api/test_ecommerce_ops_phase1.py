from fastapi.testclient import TestClient

from tests.test_api.helpers import create_test_app


def create_test_client() -> TestClient:
    return TestClient(create_test_app())


def test_ecommerce_ops_health():
    client = create_test_client()

    response = client.get("/api/v1/ecommerce-ops/health")

    assert response.status_code == 200
    assert response.json() == {
        "service": "ecommerce-ops",
        "status": "healthy",
        "phase": "phase-20-interview-package",
    }


def test_contract_registry_lists_phase_2_schemas():
    client = create_test_client()

    response = client.get("/api/v1/ecommerce-ops/contracts")

    assert response.status_code == 200
    registry = response.json()
    assert registry["version"] == "v1"
    assert "InventoryAgentInput" in registry["agent_inputs"]
    assert "DailyOpsReport" in registry["control_contracts"]
    assert "DailyOpsRunResponse" in registry["control_contracts"]
    assert "DailyOpsWorkflowState" in registry["control_contracts"]
    assert "AuditLogEntry" in registry["control_contracts"]
    assert "PromptConfig" in registry["control_contracts"]
    assert "LLMGatewayResponse" in registry["control_contracts"]
    assert "InMemoryLLMCache" in registry["control_contracts"]
    assert "APIKeyAuth" in registry["control_contracts"]
    assert "UntrustedTextSanitizer" in registry["control_contracts"]
    assert "WorkflowStartResponse" in registry["control_contracts"]
    assert "TemporalWorkflowRuntime" in registry["control_contracts"]
    assert "DockerDeployment" in registry["control_contracts"]
    assert "EvalSuite" in registry["control_contracts"]
    assert "EvalSuiteResult" in registry["control_contracts"]
    assert "InterviewPackage" in registry["control_contracts"]
    assert "POST /api/v1/ecommerce-ops/workflows/daily-ops/run" in registry["available_agent_runs"]
    assert "POST /api/v1/ecommerce-ops/workflows/daily-ops/temporal/start" in registry["available_agent_runs"]
    assert "POST /api/v1/ecommerce-ops/agents/inventory/run" in registry["available_agent_runs"]
    assert "POST /api/v1/ecommerce-ops/agents/pricing/run" in registry["available_agent_runs"]
    assert "POST /api/v1/ecommerce-ops/agents/customer-insights/run" in registry["available_agent_runs"]
    assert "POST /api/v1/ecommerce-ops/agents/marketing/run" in registry["available_agent_runs"]
    assert "GET /api/v1/ecommerce-ops/db/products" in registry["available_agent_runs"]
    assert "GET /api/v1/ecommerce-ops/approvals" in registry["available_agent_runs"]
    assert "GET /api/v1/ecommerce-ops/observability/audit-logs" in registry["available_agent_runs"]
    assert "POST /api/v1/ecommerce-ops/approvals/{approval_id}/approve" in registry["available_agent_runs"]
    assert "POST /api/v1/ecommerce-ops/approvals/{approval_id}/reject" in registry["available_agent_runs"]
    assert "PATCH /api/v1/ecommerce-ops/inventory/{sku}" in registry["available_agent_runs"]
    assert "POST /api/v1/ecommerce-ops/reviews" in registry["available_agent_runs"]
    assert "POST /api/v1/ecommerce-ops/returns" in registry["available_agent_runs"]
    assert "POST /api/v1/ecommerce-ops/competitors" in registry["available_agent_runs"]


def test_list_products_returns_seeded_catalog():
    client = create_test_client()

    response = client.get("/api/v1/ecommerce-ops/products")

    assert response.status_code == 200
    products = response.json()
    assert len(products) == 3
    assert products[0]["sku"] == "SKU-1001"
    assert products[0]["price"] > products[0]["cost"]


def test_list_inventory_exposes_stock_controls():
    client = create_test_client()

    response = client.get("/api/v1/ecommerce-ops/inventory")

    assert response.status_code == 200
    inventory = response.json()
    critical_item = next(item for item in inventory if item["sku"] == "SKU-1002")
    assert critical_item["status"] == "critical"
    assert critical_item["supplier_lead_time_days"] == 10
    assert critical_item["safety_stock"] == 15


def test_list_orders_returns_order_items():
    client = create_test_client()

    response = client.get("/api/v1/ecommerce-ops/orders")

    assert response.status_code == 200
    orders = response.json()
    assert orders[0]["order_id"] == "ORD-9001"
    assert orders[0]["items"][0]["sku"] == "SKU-1001"
    assert orders[0]["total_amount"] == 2998


def test_list_returns_contains_reason_and_evidence():
    client = create_test_client()

    response = client.get("/api/v1/ecommerce-ops/returns")

    assert response.status_code == 200
    returns = response.json()
    assert returns[0]["reason"] == "size_mismatch"
    assert "shoe runs one size small" in returns[0]["notes"]


def test_list_reviews_treats_customer_text_as_data():
    client = create_test_client()

    response = client.get("/api/v1/ecommerce-ops/reviews")

    assert response.status_code == 200
    reviews = response.json()
    assert reviews[0]["rating"] == 3
    assert reviews[0]["body"]


def test_list_competitors_includes_freshness_and_confidence_fields():
    client = create_test_client()

    response = client.get("/api/v1/ecommerce-ops/competitors")

    assert response.status_code == 200
    competitors = response.json()
    assert competitors[0]["competitor"] == "RunKart"
    assert competitors[0]["confidence"] == 0.91
    assert competitors[0]["observed_at"].endswith("Z")
