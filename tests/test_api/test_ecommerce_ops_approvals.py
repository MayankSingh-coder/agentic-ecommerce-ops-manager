from fastapi.testclient import TestClient

from tests.test_api.helpers import create_test_app


def test_pricing_run_creates_pending_approval_and_approve_api_decides_it():
    client = TestClient(create_test_app())

    pricing_response = client.post(
        "/api/v1/ecommerce-ops/agents/pricing/run",
        json={"run_id": "pricing-approval-api-test", "stale_reference_time": True},
    )
    assert pricing_response.status_code == 200

    approvals_response = client.get("/api/v1/ecommerce-ops/approvals")
    assert approvals_response.status_code == 200
    approvals = approvals_response.json()
    assert len(approvals) == 1
    assert approvals[0]["run_id"] == "pricing-approval-api-test"
    assert approvals[0]["agent_name"] == "pricing"
    assert approvals[0]["resource_type"] == "pricing_recommendation"
    assert approvals[0]["status"] == "pending"

    approval_id = approvals[0]["approval_id"]
    decision_response = client.post(
        f"/api/v1/ecommerce-ops/approvals/{approval_id}/approve",
        json={"decided_by": "ops-manager"},
    )

    assert decision_response.status_code == 200
    decided = decision_response.json()
    assert decided["status"] == "approved"
    assert decided["decided_by"] == "ops-manager"
    assert decided["decided_at"] is not None


def test_reject_unknown_approval_returns_404():
    client = TestClient(create_test_app())

    response = client.post(
        "/api/v1/ecommerce-ops/approvals/missing/reject",
        json={"decided_by": "ops-manager"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Approval request not found"
