from dataclasses import dataclass, field
from datetime import datetime, timezone
import time
from typing import TYPE_CHECKING, Callable

from app.ecommerce_ops.contracts import (
    AgentContext,
    AgentName,
    AgentRunRecord,
    AgentRunStatus,
    ApprovalRequest,
    ApprovalStatus,
    CustomerInsightAgentRunResponse,
    DailyOpsReport,
    DailyOpsRunResponse,
    InventoryAgentRunResponse,
    MarketingAgentRunResponse,
    PricingAgentRunResponse,
)

if TYPE_CHECKING:
    from app.ecommerce_ops.service import EcommerceOpsService


@dataclass
class DailyOpsWorkflowState:
    context: AgentContext
    lookback_days: int
    channels: list
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    node_history: list[str] = field(default_factory=list)
    inventory_response: InventoryAgentRunResponse | None = None
    insight_response: CustomerInsightAgentRunResponse | None = None
    pricing_response: PricingAgentRunResponse | None = None
    marketing_response: MarketingAgentRunResponse | None = None
    approvals: list[ApprovalRequest] = field(default_factory=list)
    report: DailyOpsReport | None = None
    response: DailyOpsRunResponse | None = None


class DailyOpsGraphWorkflow:
    def __init__(self) -> None:
        self.nodes: list[tuple[str, Callable[["EcommerceOpsService", DailyOpsWorkflowState], None]]] = [
            ("inventory", self._run_inventory),
            ("customer_insight", self._run_customer_insight),
            ("pricing", self._run_pricing),
            ("marketing", self._run_marketing),
            ("approval_collection", self._collect_approvals),
            ("report_build", self._build_report),
            ("summary_generation", self._generate_summary),
            ("report_persist", self._persist_report),
        ]

    def run(
        self,
        service: "EcommerceOpsService",
        context: AgentContext,
        lookback_days: int,
        channels: list,
    ) -> DailyOpsRunResponse:
        state = self.execute(
            service=service,
            context=context,
            lookback_days=lookback_days,
            channels=channels,
        )
        if state.response is None:
            raise RuntimeError("Daily ops graph completed without a response")
        return state.response

    def execute(
        self,
        service: "EcommerceOpsService",
        context: AgentContext,
        lookback_days: int,
        channels: list,
    ) -> DailyOpsWorkflowState:
        state = DailyOpsWorkflowState(
            context=context,
            lookback_days=lookback_days,
            channels=channels,
        )
        for node_name, node in self.nodes:
            node_started_at = time.perf_counter()
            try:
                node(service, state)
            except Exception as exc:
                service.record_audit_log(
                    actor=AgentName.orchestrator.value,
                    action="workflow_node_failed",
                    resource_type="daily_ops_workflow",
                    resource_id=context.run_id,
                    payload={
                        "run_id": context.run_id,
                        "node": node_name,
                        "node_index": len(state.node_history),
                        "duration_ms": int((time.perf_counter() - node_started_at) * 1000),
                        "error": str(exc),
                    },
                )
                raise
            else:
                state.node_history.append(node_name)
                service.record_audit_log(
                    actor=AgentName.orchestrator.value,
                    action="workflow_node_completed",
                    resource_type="daily_ops_workflow",
                    resource_id=context.run_id,
                    payload={
                        "run_id": context.run_id,
                        "node": node_name,
                        "node_index": len(state.node_history) - 1,
                        "duration_ms": int((time.perf_counter() - node_started_at) * 1000),
                    },
                )
        return state

    def _run_inventory(self, service: "EcommerceOpsService", state: DailyOpsWorkflowState) -> None:
        state.inventory_response = service.run_inventory_agent(
            context=state.context,
            lookback_days=state.lookback_days,
        )

    def _run_customer_insight(self, service: "EcommerceOpsService", state: DailyOpsWorkflowState) -> None:
        state.insight_response = service.run_customer_insight_agent(
            context=state.context,
            lookback_days=state.lookback_days,
        )

    def _run_pricing(self, service: "EcommerceOpsService", state: DailyOpsWorkflowState) -> None:
        state.pricing_response = service.run_pricing_agent(context=state.context)

    def _run_marketing(self, service: "EcommerceOpsService", state: DailyOpsWorkflowState) -> None:
        if state.inventory_response is None or state.insight_response is None:
            raise RuntimeError("Marketing node requires inventory and customer insight outputs")
        state.marketing_response = service.run_marketing_agent(
            context=state.context,
            channels=state.channels,
            inventory_recommendations=state.inventory_response.recommendations,
            customer_insights=state.insight_response.report,
            lookback_days=state.lookback_days,
        )

    def _collect_approvals(self, service: "EcommerceOpsService", state: DailyOpsWorkflowState) -> None:
        state.approvals = [
            approval
            for approval in service.list_approval_requests()
            if approval.run_id == state.context.run_id
        ]

    def _build_report(self, service: "EcommerceOpsService", state: DailyOpsWorkflowState) -> None:
        if state.inventory_response is None:
            raise RuntimeError("Report node requires inventory output")
        if state.insight_response is None:
            raise RuntimeError("Report node requires customer insight output")
        if state.pricing_response is None:
            raise RuntimeError("Report node requires pricing output")
        if state.marketing_response is None:
            raise RuntimeError("Report node requires marketing output")

        state.report = DailyOpsReport(
            report_date=state.context.created_at.date(),
            inventory_alerts=[
                item
                for item in state.inventory_response.recommendations
                if item.reorder_needed
            ],
            pricing_recommendations=state.pricing_response.recommendations,
            marketing_drafts=state.marketing_response.drafts,
            customer_issues=state.insight_response.report.clusters,
            approvals_required=[
                approval
                for approval in state.approvals
                if approval.status == ApprovalStatus.pending
            ],
            actions_completed=service._daily_completed_actions(
                inventory_count=len(state.inventory_response.recommendations),
                pricing_count=len(state.pricing_response.recommendations),
                marketing_count=len(state.marketing_response.drafts),
            ),
            actions_blocked=service._daily_blocked_actions(state.marketing_response.drafts),
            executive_summary="",
        )

    def _generate_summary(self, service: "EcommerceOpsService", state: DailyOpsWorkflowState) -> None:
        if state.report is None:
            raise RuntimeError("Summary node requires report output")
        state.report.executive_summary = service.llm_gateway.generate_text(
            prompt_id="daily_ops_summary_v1",
            agent=AgentName.orchestrator.value,
            input_data=state.report.model_dump(mode="json"),
        ).output

    def _persist_report(self, service: "EcommerceOpsService", state: DailyOpsWorkflowState) -> None:
        if state.report is None:
            raise RuntimeError("Persist node requires report output")
        completed_at = datetime.now(timezone.utc)
        run_record = AgentRunRecord(
            run_id=state.context.run_id,
            agent_name=AgentName.orchestrator,
            status=AgentRunStatus.succeeded,
            prompt_version="daily_ops_orchestrator_graph_v1",
            input_schema="DailyOpsRunRequest.v1",
            output_schema="DailyOpsReport.v1",
            started_at=state.started_at,
            completed_at=completed_at,
        )
        service._persist_agent_output(
            run_record=run_record,
            output_type="daily_ops_report",
            payload=state.report,
        )
        state.response = DailyOpsRunResponse(run=run_record, report=state.report)
