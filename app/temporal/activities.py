from datetime import datetime, timezone

from app.database.session import SessionLocal
from app.ecommerce_ops.contracts import (
    AgentContext,
    AgentName,
    AgentRunRecord,
    AgentRunStatus,
    DailyOpsReport,
    DailyOpsRunRequest,
    DailyOpsRunResponse,
    MarketingChannel,
)
from app.ecommerce_ops.repository_db import SqlAlchemyEcommerceOpsRepository
from app.ecommerce_ops.service import EcommerceOpsService
from temporalio import activity


def _build_context(request: DailyOpsRunRequest) -> AgentContext:
    run_id = request.run_id or request.workflow_run_id or "daily-ops-temporal"
    return AgentContext(
        run_id=run_id,
        workflow_run_id=request.workflow_run_id or run_id,
        prompt_version="daily_ops_orchestrator_graph_v1",
        triggered_by=request.triggered_by,
        created_at=datetime.now(timezone.utc),
    )


def _service_from_session(session) -> EcommerceOpsService:
    return EcommerceOpsService(SqlAlchemyEcommerceOpsRepository(session))


@activity.defn(name="run_inventory_activity")
async def run_inventory_activity(request_payload: dict) -> dict:
    request = DailyOpsRunRequest(**request_payload)
    session = SessionLocal()
    try:
        response = _service_from_session(session).run_inventory_agent(
            context=_build_context(request),
            lookback_days=request.lookback_days,
        )
        return response.model_dump(mode="json")
    finally:
        session.close()


@activity.defn(name="run_customer_insight_activity")
async def run_customer_insight_activity(request_payload: dict) -> dict:
    request = DailyOpsRunRequest(**request_payload)
    session = SessionLocal()
    try:
        response = _service_from_session(session).run_customer_insight_agent(
            context=_build_context(request),
            lookback_days=request.lookback_days,
        )
        return response.model_dump(mode="json")
    finally:
        session.close()


@activity.defn(name="run_pricing_activity")
async def run_pricing_activity(request_payload: dict) -> dict:
    request = DailyOpsRunRequest(**request_payload)
    session = SessionLocal()
    try:
        response = _service_from_session(session).run_pricing_agent(
            context=_build_context(request),
        )
        return response.model_dump(mode="json")
    finally:
        session.close()


@activity.defn(name="run_marketing_activity")
async def run_marketing_activity(activity_payload: dict) -> dict:
    request = DailyOpsRunRequest(**activity_payload["request"])
    channels = [MarketingChannel(channel) for channel in activity_payload["channels"]]
    session = SessionLocal()
    try:
        response = _service_from_session(session).run_marketing_agent(
            context=_build_context(request),
            channels=channels,
            inventory_recommendations=activity_payload["inventory_recommendations"],
            customer_insights=activity_payload["customer_insights"],
            lookback_days=request.lookback_days,
        )
        return response.model_dump(mode="json")
    finally:
        session.close()


@activity.defn(name="build_daily_report_activity")
async def build_daily_report_activity(activity_payload: dict) -> dict:
    request = DailyOpsRunRequest(**activity_payload["request"])
    context = _build_context(request)
    session = SessionLocal()
    try:
        service = _service_from_session(session)
        approvals = [
            approval
            for approval in service.list_approval_requests()
            if approval.run_id == context.run_id
        ]
        report = DailyOpsReport(
            report_date=context.created_at.date(),
            inventory_alerts=[
                item
                for item in activity_payload["inventory"]["recommendations"]
                if item["reorder_needed"]
            ],
            pricing_recommendations=activity_payload["pricing"]["recommendations"],
            marketing_drafts=activity_payload["marketing"]["drafts"],
            customer_issues=activity_payload["customer_insight"]["report"]["clusters"],
            approvals_required=[
                approval
                for approval in approvals
                if approval.status.value == "pending"
            ],
            actions_completed=service._daily_completed_actions(
                inventory_count=len(activity_payload["inventory"]["recommendations"]),
                pricing_count=len(activity_payload["pricing"]["recommendations"]),
                marketing_count=len(activity_payload["marketing"]["drafts"]),
            ),
            actions_blocked=[],
            executive_summary="",
        )
        report.actions_blocked = service._daily_blocked_actions(report.marketing_drafts)
        report.executive_summary = service.llm_gateway.generate_text(
            prompt_id="daily_ops_summary_v1",
            agent=AgentName.orchestrator.value,
            input_data=report.model_dump(mode="json"),
        ).output
        completed_at = datetime.now(timezone.utc)
        run_record = AgentRunRecord(
            run_id=context.run_id,
            agent_name=AgentName.orchestrator,
            status=AgentRunStatus.succeeded,
            prompt_version="daily_ops_orchestrator_graph_v1",
            input_schema="DailyOpsRunRequest.v1",
            output_schema="DailyOpsReport.v1",
            started_at=context.created_at,
            completed_at=completed_at,
        )
        service._persist_agent_output(
            run_record=run_record,
            output_type="daily_ops_report",
            payload=report,
        )
        response = DailyOpsRunResponse(run=run_record, report=report)
        return response.model_dump(mode="json")
    finally:
        session.close()


@activity.defn(name="run_daily_ops_activity")
async def run_daily_ops_activity(request_payload: dict) -> dict:
    request = DailyOpsRunRequest(**request_payload)
    session = SessionLocal()
    try:
        response = _service_from_session(session).run_daily_ops_workflow(
            context=_build_context(request),
            lookback_days=request.lookback_days,
            channels=request.channels,
        )
        return response.model_dump(mode="json")
    finally:
        session.close()
