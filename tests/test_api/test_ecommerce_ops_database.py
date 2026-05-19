from sqlalchemy import create_engine, inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.database.models import AgentRunModel
from app.database.models import Base
from app.database.seed import seed_demo_data
from app.ecommerce_ops.agents.inventory_agent import InventoryAgent
from app.ecommerce_ops.contracts import AgentContext, AgentName, AgentRunRecord, AgentRunStatus, InventoryAgentInput
from app.ecommerce_ops.repository_db import SqlAlchemyEcommerceOpsRepository
from app.ecommerce_ops.service import EcommerceOpsService

from datetime import datetime, timezone
from pathlib import Path


def create_test_session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine)
    return engine, session_factory()


def test_database_schema_contains_operational_and_control_tables():
    engine, session = create_test_session()
    try:
        table_names = set(inspect(engine).get_table_names())
    finally:
        session.close()

    assert "products" in table_names
    assert "inventory_items" in table_names
    assert "orders" in table_names
    assert "order_items" in table_names
    assert "returns" in table_names
    assert "reviews" in table_names
    assert "competitor_prices" in table_names
    assert "agent_runs" in table_names
    assert "agent_outputs" in table_names
    assert "approval_requests" in table_names
    assert "audit_logs" in table_names


def test_seed_demo_data_is_idempotent():
    _, session = create_test_session()
    try:
        seed_demo_data(session)
        seed_demo_data(session)
        repository = SqlAlchemyEcommerceOpsRepository(session)

        assert len(repository.list_products()) == 3
        assert len(repository.list_inventory()) == 3
        assert len(repository.list_orders()) == 2
        assert len(repository.list_returns()) == 2
        assert len(repository.list_reviews()) == 2
        assert len(repository.list_competitors()) == 2
    finally:
        session.close()


def test_seed_demo_data_flushes_products_before_fk_dependents():
    seed_source = Path("app/database/seed.py").read_text(encoding="utf-8")
    product_loop_index = seed_source.index("for product in repository.list_products()")
    flush_index = seed_source.index("session.flush()")
    inventory_loop_index = seed_source.index("for item in repository.list_inventory()")

    assert product_loop_index < flush_index < inventory_loop_index


def test_db_repository_feeds_inventory_agent_without_schema_changes():
    _, session = create_test_session()
    try:
        seed_demo_data(session)
        repository = SqlAlchemyEcommerceOpsRepository(session)
        agent_input = InventoryAgentInput(
            context=AgentContext(
                run_id="db-inventory-test",
                prompt_version="inventory_agent_rules_v1",
                created_at=datetime.now(timezone.utc),
            ),
            products=repository.list_products(),
            inventory=repository.list_inventory(),
            orders=repository.list_orders(),
            lookback_days=30,
        )

        recommendations, run_record = InventoryAgent().run(agent_input)

        assert run_record.run_id == "db-inventory-test"
        assert len(recommendations) == 3
        assert recommendations[0].sku == "SKU-1001"
    finally:
        session.close()


def test_db_backed_service_persists_agent_run_and_output():
    _, session = create_test_session()
    try:
        seed_demo_data(session)
        repository = SqlAlchemyEcommerceOpsRepository(session)
        service = EcommerceOpsService(repository)

        service.run_inventory_agent(
            context=AgentContext(
                run_id="persisted-inventory-run",
                prompt_version="inventory_agent_rules_v1",
                created_at=datetime.now(timezone.utc),
            )
        )

        outputs = repository.list_agent_outputs("persisted-inventory-run")
        assert repository.count_agent_runs() == 1
        assert len(outputs) == 1
        assert "SKU-1001" in outputs[0]
    finally:
        session.close()


def test_db_repository_allows_same_workflow_run_across_multiple_agents():
    _, session = create_test_session()
    try:
        repository = SqlAlchemyEcommerceOpsRepository(session)
        started_at = datetime.now(timezone.utc)
        for agent_name in [AgentName.inventory, AgentName.customer_insight]:
            repository.save_agent_run(
                AgentRunRecord(
                    run_id="shared-workflow-run",
                    agent_name=agent_name,
                    status=AgentRunStatus.succeeded,
                    prompt_version=f"{agent_name.value}_v1",
                    input_schema="input.v1",
                    output_schema="output.v1",
                    started_at=started_at,
                    completed_at=started_at,
                ),
                output_type=f"{agent_name.value}_output",
                payload={"agent": agent_name.value},
            )

        assert repository.count_agent_runs() == 2
        assert len(repository.list_agent_outputs("shared-workflow-run")) == 2
    finally:
        session.close()


def test_agent_runs_are_unique_per_run_id_and_agent_name():
    _, session = create_test_session()
    try:
        started_at = datetime.now(timezone.utc)
        session.add(
            AgentRunModel(
                run_id="unique-workflow-run",
                agent_name=AgentName.inventory.value,
                status=AgentRunStatus.succeeded.value,
                prompt_version="inventory_v1",
                input_schema="input.v1",
                output_schema="output.v1",
                started_at=started_at,
                completed_at=started_at,
            )
        )
        session.add(
            AgentRunModel(
                run_id="unique-workflow-run",
                agent_name=AgentName.inventory.value,
                status=AgentRunStatus.succeeded.value,
                prompt_version="inventory_v1",
                input_schema="input.v1",
                output_schema="output.v1",
                started_at=started_at,
                completed_at=started_at,
            )
        )

        try:
            session.commit()
        except IntegrityError:
            session.rollback()
        else:
            raise AssertionError("duplicate agent run should fail unique constraint")
    finally:
        session.close()


def test_db_repository_persists_and_decides_approval_request():
    _, session = create_test_session()
    try:
        seed_demo_data(session)
        repository = SqlAlchemyEcommerceOpsRepository(session)
        service = EcommerceOpsService(repository)
        pricing_response = service.run_pricing_agent(
            context=AgentContext(
                run_id="approval-pricing-run",
                prompt_version="pricing_agent_rules_v1",
                created_at=datetime(2026, 5, 20, 12, 0, tzinfo=timezone.utc),
            )
        )

        approval_required = [
            recommendation
            for recommendation in pricing_response.recommendations
            if recommendation.requires_approval
        ]
        approvals = service.list_approval_requests()

        assert approval_required
        assert len(approvals) == len(approval_required)
        decided = service.approve_request(approvals[0].approval_id, "ops-manager")
        assert decided is not None
        assert decided.status.value == "approved"
        assert decided.decided_by == "ops-manager"
    finally:
        session.close()
