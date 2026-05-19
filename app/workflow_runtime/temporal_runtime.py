from uuid import uuid4

from app.config import settings
from app.ecommerce_ops.contracts import DailyOpsRunRequest, WorkflowStartResponse


class TemporalRuntimeUnavailable(RuntimeError):
    pass


class TemporalWorkflowRuntime:
    runtime_name = "temporal"
    workflow_type = "DailyOpsTemporalWorkflow"

    async def start_daily_ops_workflow(
        self,
        request: DailyOpsRunRequest,
        workflow_id: str | None = None,
        task_queue: str | None = None,
    ) -> WorkflowStartResponse:
        try:
            from temporalio.client import Client
        except ImportError as exc:
            raise TemporalRuntimeUnavailable(
                "temporalio is not installed. Install requirements and run Temporal before using this endpoint."
            ) from exc

        resolved_workflow_id = workflow_id or request.workflow_run_id or request.run_id or f"daily-ops-{uuid4()}"
        resolved_task_queue = task_queue or settings.temporal_task_queue
        client = await Client.connect(
            settings.temporal_address,
            namespace=settings.temporal_namespace,
        )
        handle = await client.start_workflow(
            self.workflow_type,
            request.model_dump(mode="json"),
            id=resolved_workflow_id,
            task_queue=resolved_task_queue,
        )
        return WorkflowStartResponse(
            workflow_id=handle.id,
            run_id=request.run_id or resolved_workflow_id,
            task_queue=resolved_task_queue,
            runtime=self.runtime_name,
            status="started",
        )
