from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.ecommerce_ops.contracts import AgentContext
from app.ecommerce_ops.repository_db import SqlAlchemyEcommerceOpsRepository
from app.ecommerce_ops.service import EcommerceOpsService
from tests.test_api.helpers import create_test_app
from tests.test_api.test_ecommerce_ops_database import create_test_session
from app.database.seed import seed_demo_data


def test_daily_ops_workflow_returns_structured_report_and_persists_output():
    _, session = create_test_session()
    try:
        seed_demo_data(session)
        repository = SqlAlchemyEcommerceOpsRepository(session)
        service = EcommerceOpsService(repository)

        response = service.run_daily_ops_workflow(
            context=AgentContext(
                run_id="daily-ops-service-test",
                workflow_run_id="daily-ops-service-test",
                prompt_version="daily_ops_orchestrator_rules_v1",
                created_at=datetime.now(timezone.utc),
            ),
            lookback_days=30,
            channels=["email"],
        )

        assert response.run.agent_name.value == "orchestrator"
        assert response.report.inventory_alerts
        assert response.report.pricing_recommendations
        assert response.report.marketing_drafts
        assert response.report.customer_issues
        assert response.report.actions_completed
        assert response.report.actions_blocked
        assert "Daily ops completed" in response.report.executive_summary
        assert repository.count_agent_runs() == 5
        assert len(repository.list_agent_outputs("daily-ops-service-test")) == 5
    finally:
        session.close()


def test_daily_ops_workflow_api_returns_report_sections():
    client = TestClient(create_test_app())

    response = client.post(
        "/api/v1/ecommerce-ops/workflows/daily-ops/run",
        json={"run_id": "daily-ops-api-test", "channels": ["email"], "lookback_days": 30},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["run"]["agent_name"] == "orchestrator"
    assert payload["run"]["run_id"] == "daily-ops-api-test"
    assert payload["report"]["inventory_alerts"]
    assert payload["report"]["pricing_recommendations"]
    assert payload["report"]["marketing_drafts"]
    assert payload["report"]["customer_issues"]
    assert payload["report"]["actions_completed"]
    assert payload["report"]["actions_blocked"]
    assert "pending approvals" in payload["report"]["executive_summary"]
