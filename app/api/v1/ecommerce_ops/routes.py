from datetime import datetime, timezone
from datetime import timedelta
from typing import List
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ....ecommerce_ops.contracts import (
    AgentContext,
    ApprovalDecisionRequest,
    ApprovalRequest,
    AuditLogEntry,
    CustomerInsightAgentRunRequest,
    CustomerInsightAgentRunResponse,
    DailyOpsRunRequest,
    DailyOpsRunResponse,
    InventoryUpdateRequest,
    InventoryAgentRunRequest,
    InventoryAgentRunResponse,
    MarketingAgentRunRequest,
    MarketingAgentRunResponse,
    PricingAgentRunRequest,
    PricingAgentRunResponse,
    WorkflowStartResponse,
)
from ....database.session import get_db_session
from ....ecommerce_ops.repository import EcommerceOpsRepository
from ....ecommerce_ops.repository_db import SqlAlchemyEcommerceOpsRepository
from ....ecommerce_ops.schemas import (
    CompetitorPrice,
    InventoryItem,
    Order,
    Product,
    ProductReturn,
    Review,
)
from ....ecommerce_ops.service import EcommerceOpsService
from ....security.api_key import require_api_key
from ....workflow_runtime.temporal_runtime import TemporalRuntimeUnavailable, TemporalWorkflowRuntime

router = APIRouter(
    prefix="/ecommerce-ops",
    tags=["E-Commerce Ops"],
    dependencies=[Depends(require_api_key)],
)


def get_ecommerce_ops_service() -> EcommerceOpsService:
    return EcommerceOpsService(EcommerceOpsRepository())


def get_ecommerce_ops_db_service(
    session: Session = Depends(get_db_session),
) -> EcommerceOpsService:
    return EcommerceOpsService(SqlAlchemyEcommerceOpsRepository(session))


def get_workflow_runtime() -> TemporalWorkflowRuntime:
    return TemporalWorkflowRuntime()


@router.get("/health")
async def health(service: EcommerceOpsService = Depends(get_ecommerce_ops_service)):
    return service.health()


@router.get("/contracts")
async def contract_registry(
    service: EcommerceOpsService = Depends(get_ecommerce_ops_service),
):
    return service.contract_registry()


@router.get("/approvals", response_model=List[ApprovalRequest])
async def list_approvals(
    service: EcommerceOpsService = Depends(get_ecommerce_ops_db_service),
):
    return service.list_approval_requests()


@router.get("/observability/audit-logs", response_model=List[AuditLogEntry])
async def list_audit_logs(
    run_id: str | None = Query(default=None),
    service: EcommerceOpsService = Depends(get_ecommerce_ops_db_service),
):
    return service.list_audit_logs(run_id=run_id)


@router.post("/workflows/daily-ops/run", response_model=DailyOpsRunResponse)
async def run_daily_ops_workflow(
    request: DailyOpsRunRequest,
    service: EcommerceOpsService = Depends(get_ecommerce_ops_db_service),
):
    context = AgentContext(
        run_id=request.run_id or f"daily-ops-{uuid4()}",
        workflow_run_id=request.workflow_run_id or request.run_id,
        prompt_version="daily_ops_orchestrator_rules_v1",
        triggered_by=request.triggered_by,
        created_at=datetime.now(timezone.utc),
    )
    return service.run_daily_ops_workflow(
        context=context,
        lookback_days=request.lookback_days,
        channels=request.channels,
    )


@router.post("/workflows/daily-ops/temporal/start", response_model=WorkflowStartResponse)
async def start_daily_ops_temporal_workflow(
    request: DailyOpsRunRequest,
    runtime: TemporalWorkflowRuntime = Depends(get_workflow_runtime),
):
    try:
        return await runtime.start_daily_ops_workflow(request)
    except TemporalRuntimeUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/approvals/{approval_id}/approve", response_model=ApprovalRequest)
async def approve_request(
    approval_id: str,
    request: ApprovalDecisionRequest,
    service: EcommerceOpsService = Depends(get_ecommerce_ops_db_service),
):
    approval = service.approve_request(approval_id, request.decided_by)
    if approval is None:
        raise HTTPException(status_code=404, detail="Approval request not found")
    return approval


@router.post("/approvals/{approval_id}/reject", response_model=ApprovalRequest)
async def reject_request(
    approval_id: str,
    request: ApprovalDecisionRequest,
    service: EcommerceOpsService = Depends(get_ecommerce_ops_db_service),
):
    approval = service.reject_request(approval_id, request.decided_by)
    if approval is None:
        raise HTTPException(status_code=404, detail="Approval request not found")
    return approval


@router.post("/agents/inventory/run", response_model=InventoryAgentRunResponse)
async def run_inventory_agent(
    request: InventoryAgentRunRequest,
    service: EcommerceOpsService = Depends(get_ecommerce_ops_db_service),
):
    context = AgentContext(
        run_id=request.run_id or f"inventory-{uuid4()}",
        workflow_run_id=request.workflow_run_id,
        prompt_version=request.prompt_version,
        triggered_by=request.triggered_by,
        created_at=datetime.now(timezone.utc),
    )
    return service.run_inventory_agent(
        context=context,
        lookback_days=request.lookback_days,
    )


@router.post("/agents/pricing/run", response_model=PricingAgentRunResponse)
async def run_pricing_agent(
    request: PricingAgentRunRequest,
    service: EcommerceOpsService = Depends(get_ecommerce_ops_db_service),
):
    created_at = datetime.now(timezone.utc)
    if request.stale_reference_time:
        created_at = created_at + timedelta(days=3)
    context = AgentContext(
        run_id=request.run_id or f"pricing-{uuid4()}",
        workflow_run_id=request.workflow_run_id,
        prompt_version=request.prompt_version,
        triggered_by=request.triggered_by,
        created_at=created_at,
    )
    return service.run_pricing_agent(context=context)


@router.post("/agents/customer-insights/run", response_model=CustomerInsightAgentRunResponse)
async def run_customer_insight_agent(
    request: CustomerInsightAgentRunRequest,
    service: EcommerceOpsService = Depends(get_ecommerce_ops_db_service),
):
    context = AgentContext(
        run_id=request.run_id or f"customer-insight-{uuid4()}",
        workflow_run_id=request.workflow_run_id,
        prompt_version=request.prompt_version,
        triggered_by=request.triggered_by,
        created_at=datetime.now(timezone.utc),
    )
    return service.run_customer_insight_agent(
        context=context,
        lookback_days=request.lookback_days,
    )


@router.post("/agents/marketing/run", response_model=MarketingAgentRunResponse)
async def run_marketing_agent(
    request: MarketingAgentRunRequest,
    service: EcommerceOpsService = Depends(get_ecommerce_ops_db_service),
):
    context = AgentContext(
        run_id=request.run_id or f"marketing-{uuid4()}",
        workflow_run_id=request.workflow_run_id,
        prompt_version=request.prompt_version,
        triggered_by=request.triggered_by,
        created_at=datetime.now(timezone.utc),
    )
    return service.run_marketing_agent(
        context=context,
        channels=request.channels,
    )


@router.get("/products", response_model=List[Product])
async def list_products(
    service: EcommerceOpsService = Depends(get_ecommerce_ops_db_service),
):
    return service.list_products()


@router.get("/db/products", response_model=List[Product])
async def list_db_products(
    service: EcommerceOpsService = Depends(get_ecommerce_ops_db_service),
):
    return service.list_products()


@router.get("/inventory", response_model=List[InventoryItem])
async def list_inventory(
    service: EcommerceOpsService = Depends(get_ecommerce_ops_db_service),
):
    return service.list_inventory()


@router.get("/orders", response_model=List[Order])
async def list_orders(
    service: EcommerceOpsService = Depends(get_ecommerce_ops_db_service),
):
    return service.list_orders()


@router.get("/returns", response_model=List[ProductReturn])
async def list_returns(
    service: EcommerceOpsService = Depends(get_ecommerce_ops_db_service),
):
    return service.list_returns()


@router.get("/reviews", response_model=List[Review])
async def list_reviews(
    service: EcommerceOpsService = Depends(get_ecommerce_ops_db_service),
):
    return service.list_reviews()


@router.get("/competitors", response_model=List[CompetitorPrice])
async def list_competitors(
    service: EcommerceOpsService = Depends(get_ecommerce_ops_db_service),
):
    return service.list_competitors()


@router.patch("/inventory/{sku}", response_model=InventoryItem)
async def upsert_inventory_item(
    sku: str,
    request: InventoryUpdateRequest,
    session: Session = Depends(get_db_session),
):
    repository = SqlAlchemyEcommerceOpsRepository(session)
    try:
        return repository.upsert_inventory_item(
            InventoryItem(
                sku=sku,
                warehouse=request.warehouse,
                available_stock=request.available_stock,
                reserved_stock=request.reserved_stock,
                reorder_point=request.reorder_point,
                supplier_lead_time_days=request.supplier_lead_time_days,
                safety_stock=request.safety_stock,
                status=request.status,
            )
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/reviews", response_model=Review)
async def add_review(
    review: Review,
    session: Session = Depends(get_db_session),
):
    repository = SqlAlchemyEcommerceOpsRepository(session)
    try:
        return repository.add_review(review)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/returns", response_model=ProductReturn)
async def add_return(
    product_return: ProductReturn,
    session: Session = Depends(get_db_session),
):
    repository = SqlAlchemyEcommerceOpsRepository(session)
    try:
        return repository.add_return(product_return)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/competitors", response_model=CompetitorPrice)
async def add_competitor_price(
    competitor_price: CompetitorPrice,
    session: Session = Depends(get_db_session),
):
    repository = SqlAlchemyEcommerceOpsRepository(session)
    try:
        return repository.add_competitor_price(competitor_price)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
