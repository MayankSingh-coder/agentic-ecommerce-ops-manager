from fastapi.testclient import TestClient

from app.api.v1.ecommerce_ops.routes import get_workflow_runtime
from app.ecommerce_ops.contracts import DailyOpsRunRequest, WorkflowStartResponse
from app.workflow_runtime.temporal_runtime import TemporalRuntimeUnavailable, TemporalWorkflowRuntime
from tests.test_api.helpers import create_test_app


class FakeTemporalWorkflowRuntime:
    async def start_daily_ops_workflow(self, request: DailyOpsRunRequest) -> WorkflowStartResponse:
        run_id = request.run_id or "temporal-test-run"
        return WorkflowStartResponse(
            workflow_id=request.workflow_run_id or run_id,
            run_id=run_id,
            task_queue="test-task-queue",
            runtime="temporal",
            status="started",
        )


class UnavailableTemporalWorkflowRuntime:
    async def start_daily_ops_workflow(self, request: DailyOpsRunRequest) -> WorkflowStartResponse:
        raise TemporalRuntimeUnavailable("Temporal is unavailable")


def test_temporal_start_endpoint_uses_workflow_runtime_dependency():
    app = create_test_app()
    app.dependency_overrides[get_workflow_runtime] = lambda: FakeTemporalWorkflowRuntime()
    client = TestClient(app)

    response = client.post(
        "/api/v1/ecommerce-ops/workflows/daily-ops/temporal/start",
        json={
            "run_id": "temporal-api-test",
            "workflow_run_id": "temporal-workflow-test",
            "channels": ["email"],
            "lookback_days": 30,
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "workflow_id": "temporal-workflow-test",
        "run_id": "temporal-api-test",
        "task_queue": "test-task-queue",
        "runtime": "temporal",
        "status": "started",
    }


def test_temporal_start_endpoint_returns_503_when_runtime_unavailable():
    app = create_test_app()
    app.dependency_overrides[get_workflow_runtime] = lambda: UnavailableTemporalWorkflowRuntime()
    client = TestClient(app)

    response = client.post(
        "/api/v1/ecommerce-ops/workflows/daily-ops/temporal/start",
        json={"run_id": "temporal-api-unavailable-test"},
    )

    assert response.status_code == 503
    assert response.json()["detail"] == "Temporal is unavailable"


def test_temporal_runtime_builds_stable_workflow_response_without_server_call(monkeypatch):
    started_payload = {}

    class FakeHandle:
        id = "daily-ops-workflow-id"

    class FakeClient:
        async def start_workflow(self, workflow_type, payload, id, task_queue):
            started_payload.update(
                {
                    "workflow_type": workflow_type,
                    "payload": payload,
                    "id": id,
                    "task_queue": task_queue,
                }
            )
            return FakeHandle()

    async def fake_connect(address, namespace):
        started_payload["address"] = address
        started_payload["namespace"] = namespace
        return FakeClient()

    import sys
    import types

    temporalio_module = types.ModuleType("temporalio")
    temporalio_client_module = types.ModuleType("temporalio.client")
    temporalio_client_module.Client = types.SimpleNamespace(connect=fake_connect)
    monkeypatch.setitem(sys.modules, "temporalio", temporalio_module)
    monkeypatch.setitem(sys.modules, "temporalio.client", temporalio_client_module)

    import asyncio

    response = asyncio.run(
        TemporalWorkflowRuntime().start_daily_ops_workflow(
            DailyOpsRunRequest(
                run_id="daily-ops-run-id",
                workflow_run_id="daily-ops-workflow-id",
            )
        )
    )

    assert response.workflow_id == "daily-ops-workflow-id"
    assert response.run_id == "daily-ops-run-id"
    assert response.status == "started"
    assert started_payload["workflow_type"] == "DailyOpsTemporalWorkflow"
    assert started_payload["id"] == "daily-ops-workflow-id"


def test_temporal_worker_retries_until_connection_succeeds(monkeypatch):
    from app.temporal import worker

    attempts = 0

    class FakeClient:
        pass

    async def fake_connect():
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("dns not ready")
        return FakeClient()

    async def no_sleep(delay_seconds):
        return None

    monkeypatch.setattr(worker, "connect_temporal_once", fake_connect)
    monkeypatch.setattr(worker.asyncio, "sleep", no_sleep)

    import asyncio

    client = asyncio.run(
        worker.connect_temporal_with_retry(max_attempts=2, delay_seconds=0)
    )

    assert isinstance(client, FakeClient)
    assert attempts == 2


def test_temporal_daily_ops_activity_is_registered_with_sdk():
    from app.temporal.activities import (
        build_daily_report_activity,
        run_customer_insight_activity,
        run_daily_ops_activity,
        run_inventory_activity,
        run_marketing_activity,
        run_pricing_activity,
    )

    activities = [
        (run_inventory_activity, "run_inventory_activity"),
        (run_customer_insight_activity, "run_customer_insight_activity"),
        (run_pricing_activity, "run_pricing_activity"),
        (run_marketing_activity, "run_marketing_activity"),
        (build_daily_report_activity, "build_daily_report_activity"),
        (run_daily_ops_activity, "run_daily_ops_activity"),
    ]

    for activity, expected_name in activities:
        definition = getattr(activity, "__temporal_activity_definition", None)
        assert definition is not None
        assert definition.name == expected_name
        assert definition.is_async is True


def test_temporal_workflow_uses_granular_agent_activities():
    from pathlib import Path

    workflow_source = Path("app/temporal/workflows.py").read_text(encoding="utf-8")

    assert '"run_inventory_activity"' in workflow_source
    assert '"run_customer_insight_activity"' in workflow_source
    assert '"run_pricing_activity"' in workflow_source
    assert '"run_marketing_activity"' in workflow_source
    assert '"build_daily_report_activity"' in workflow_source
    assert '"run_daily_ops_activity"' not in workflow_source
