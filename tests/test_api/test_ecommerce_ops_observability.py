from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.database.seed import seed_demo_data
from app.ecommerce_ops.contracts import AgentContext
from app.ecommerce_ops.repository_db import SqlAlchemyEcommerceOpsRepository
from app.ecommerce_ops.service import EcommerceOpsService
from tests.test_api.helpers import create_test_app
from tests.test_api.test_ecommerce_ops_database import create_test_session


def test_daily_ops_workflow_persists_node_audit_events():
    _, session = create_test_session()
    try:
        seed_demo_data(session)
        service = EcommerceOpsService(SqlAlchemyEcommerceOpsRepository(session))

        service.run_daily_ops_workflow(
            context=AgentContext(
                run_id="observability-service-test",
                workflow_run_id="observability-service-test",
                prompt_version="daily_ops_orchestrator_graph_v1",
                created_at=datetime.now(timezone.utc),
            ),
            lookback_days=30,
            channels=["email"],
        )

        entries = service.list_audit_logs(run_id="observability-service-test")
        completed_nodes = [
            entry.payload["node"]
            for entry in entries
            if entry.action == "workflow_node_completed"
        ]

        assert completed_nodes == [
            "inventory",
            "customer_insight",
            "pricing",
            "marketing",
            "approval_collection",
            "report_build",
            "summary_generation",
            "report_persist",
        ]
        assert all("duration_ms" in entry.payload for entry in entries)
    finally:
        session.close()


def test_observability_audit_logs_api_filters_by_run_id():
    client = TestClient(create_test_app())

    run_id = "observability-api-test"
    workflow_response = client.post(
        "/api/v1/ecommerce-ops/workflows/daily-ops/run",
        json={"run_id": run_id, "channels": ["email"], "lookback_days": 30},
    )
    response = client.get(
        "/api/v1/ecommerce-ops/observability/audit-logs",
        params={"run_id": run_id},
    )

    assert workflow_response.status_code == 200
    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 8
    assert payload[0]["action"] == "workflow_node_completed"
    assert payload[0]["resource_id"] == run_id
    assert payload[0]["payload"]["run_id"] == run_id
