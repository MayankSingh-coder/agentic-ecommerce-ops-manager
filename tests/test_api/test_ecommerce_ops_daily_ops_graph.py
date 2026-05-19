from datetime import datetime, timezone

from app.database.seed import seed_demo_data
from app.ecommerce_ops.contracts import AgentContext
from app.ecommerce_ops.repository_db import SqlAlchemyEcommerceOpsRepository
from app.ecommerce_ops.service import EcommerceOpsService
from app.ecommerce_ops.workflows.daily_ops_graph import DailyOpsGraphWorkflow
from tests.test_api.test_ecommerce_ops_database import create_test_session


def test_daily_ops_graph_runs_nodes_in_expected_order():
    _, session = create_test_session()
    try:
        seed_demo_data(session)
        service = EcommerceOpsService(SqlAlchemyEcommerceOpsRepository(session))
        workflow = DailyOpsGraphWorkflow()

        state = workflow.execute(
            service=service,
            context=AgentContext(
                run_id="daily-ops-graph-test",
                workflow_run_id="daily-ops-graph-test",
                prompt_version="daily_ops_orchestrator_graph_v1",
                created_at=datetime.now(timezone.utc),
            ),
            lookback_days=30,
            channels=["email"],
        )

        assert state.node_history == [
            "inventory",
            "customer_insight",
            "pricing",
            "marketing",
            "approval_collection",
            "report_build",
            "summary_generation",
            "report_persist",
        ]
        assert state.response is not None
        assert state.response.run.prompt_version == "daily_ops_orchestrator_graph_v1"
        assert state.response.report.inventory_alerts
        assert state.response.report.marketing_drafts
    finally:
        session.close()


def test_daily_ops_graph_reuses_inventory_and_insight_outputs_for_marketing():
    _, session = create_test_session()
    try:
        seed_demo_data(session)
        service = EcommerceOpsService(SqlAlchemyEcommerceOpsRepository(session))
        workflow = DailyOpsGraphWorkflow()

        state = workflow.execute(
            service=service,
            context=AgentContext(
                run_id="daily-ops-graph-deps-test",
                workflow_run_id="daily-ops-graph-deps-test",
                prompt_version="daily_ops_orchestrator_graph_v1",
                created_at=datetime.now(timezone.utc),
            ),
            lookback_days=30,
            channels=["email"],
        )

        assert state.inventory_response is not None
        assert state.insight_response is not None
        assert state.marketing_response is not None
        assert len(state.marketing_response.drafts) == len(service.list_products())
    finally:
        session.close()
