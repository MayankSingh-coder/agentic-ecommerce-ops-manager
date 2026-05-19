from datetime import date, datetime
from enum import Enum
from typing import Any, List, Optional

from pydantic import BaseModel, Field, model_validator

from .schemas import (
    CompetitorPrice,
    InventoryItem,
    Order,
    Product,
    ProductReturn,
    Review,
    StockStatus,
)


class AgentName(str, Enum):
    inventory = "inventory"
    pricing = "pricing"
    marketing = "marketing"
    customer_insight = "customer_insight"
    orchestrator = "orchestrator"


class AgentRunStatus(str, Enum):
    queued = "queued"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"
    blocked = "blocked"


class RiskLevel(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


class ApprovalStatus(str, Enum):
    not_required = "not_required"
    pending = "pending"
    approved = "approved"
    rejected = "rejected"


class PolicyDecision(str, Enum):
    allowed = "allowed"
    approval_required = "approval_required"
    blocked = "blocked"


class MarketingChannel(str, Enum):
    email = "email"
    sms = "sms"
    push = "push"


class AgentContext(BaseModel):
    run_id: str
    workflow_run_id: Optional[str] = None
    prompt_version: str
    model: Optional[str] = None
    triggered_by: str = "manual"
    created_at: datetime


class InventoryAgentInput(BaseModel):
    context: AgentContext
    products: List[Product]
    inventory: List[InventoryItem]
    orders: List[Order]
    lookback_days: int = Field(default=30, ge=1, le=365)


class InventoryAgentRunRequest(BaseModel):
    run_id: Optional[str] = None
    workflow_run_id: Optional[str] = None
    prompt_version: str = "inventory_agent_rules_v1"
    triggered_by: str = "manual"
    lookback_days: int = Field(default=30, ge=1, le=365)


class InventoryRecommendation(BaseModel):
    sku: str
    warehouse: str
    available_stock: int = Field(ge=0)
    avg_daily_sales: float = Field(ge=0)
    days_of_inventory: Optional[float] = Field(default=None, ge=0)
    reorder_needed: bool
    recommended_reorder_qty: int = Field(ge=0)
    risk_level: RiskLevel
    reason: str
    requires_approval: bool = False


class PricingAgentInput(BaseModel):
    context: AgentContext
    products: List[Product]
    inventory: List[InventoryItem]
    orders: List[Order]
    competitor_prices: List[CompetitorPrice]


class PricingAgentRunRequest(BaseModel):
    run_id: Optional[str] = None
    workflow_run_id: Optional[str] = None
    prompt_version: str = "pricing_agent_rules_v1"
    triggered_by: str = "manual"
    stale_reference_time: bool = False


class PricingRecommendation(BaseModel):
    sku: str
    current_price: float = Field(gt=0)
    recommended_price: float = Field(gt=0)
    current_margin_pct: float = Field(ge=0, le=100)
    recommended_margin_pct: float = Field(ge=0, le=100)
    price_change_pct: float
    competitor_reference_price: Optional[float] = Field(default=None, gt=0)
    expected_revenue_impact: float
    confidence: float = Field(ge=0, le=1)
    risk_level: RiskLevel
    reason: str
    policy_decision: PolicyDecision
    requires_approval: bool

    @model_validator(mode="after")
    def approval_matches_policy(self):
        if self.policy_decision == PolicyDecision.approval_required and not self.requires_approval:
            raise ValueError("requires_approval must be true when policy_decision is approval_required")
        return self


class CustomerInsightAgentInput(BaseModel):
    context: AgentContext
    products: List[Product]
    reviews: List[Review]
    returns: List[ProductReturn]
    lookback_days: int = Field(default=30, ge=1, le=365)


class CustomerInsightAgentRunRequest(BaseModel):
    run_id: Optional[str] = None
    workflow_run_id: Optional[str] = None
    prompt_version: str = "customer_insight_clustering_v1"
    triggered_by: str = "manual"
    lookback_days: int = Field(default=30, ge=1, le=365)


class IssueCluster(BaseModel):
    sku: str
    issue: str
    review_count: int = Field(ge=0)
    return_count: int = Field(ge=0)
    representative_evidence: List[str] = Field(default_factory=list)
    severity: RiskLevel


class CustomerInsightReport(BaseModel):
    clusters: List[IssueCluster]
    summary: str


class MarketingAgentInput(BaseModel):
    context: AgentContext
    products: List[Product]
    inventory_recommendations: List[InventoryRecommendation]
    customer_insights: CustomerInsightReport
    channels: List[MarketingChannel] = Field(default_factory=lambda: [MarketingChannel.email])


class MarketingAgentRunRequest(BaseModel):
    run_id: Optional[str] = None
    workflow_run_id: Optional[str] = None
    prompt_version: str = "marketing_agent_rules_v1"
    triggered_by: str = "manual"
    channels: List[MarketingChannel] = Field(default_factory=lambda: [MarketingChannel.email])


class MarketingDraft(BaseModel):
    campaign_name: str
    target_skus: List[str]
    channel: MarketingChannel
    audience_segment: str
    subject_lines: List[str] = Field(default_factory=list)
    body: str
    offer: Optional[str] = None
    risk_level: RiskLevel
    requires_approval: bool = True
    blocked_reason: Optional[str] = None

    @model_validator(mode="after")
    def blocked_campaigns_need_reason(self):
        if self.risk_level in {RiskLevel.high, RiskLevel.critical} and not self.blocked_reason:
            raise ValueError("high-risk marketing drafts must include blocked_reason")
        return self


class ApprovalRequest(BaseModel):
    approval_id: str
    run_id: str
    agent_name: AgentName
    resource_type: str
    resource_id: str
    reason: str
    risk_level: RiskLevel
    status: ApprovalStatus = ApprovalStatus.pending
    created_at: datetime
    decided_at: Optional[datetime] = None
    decided_by: Optional[str] = None


class ApprovalDecisionRequest(BaseModel):
    decided_by: str


class AuditLogEntry(BaseModel):
    audit_id: Optional[int] = None
    actor: str
    action: str
    resource_type: str
    resource_id: str
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class AgentRunRecord(BaseModel):
    run_id: str
    agent_name: AgentName
    status: AgentRunStatus
    prompt_version: str
    input_schema: str
    output_schema: str
    started_at: datetime
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None


class InventoryAgentRunResponse(BaseModel):
    run: AgentRunRecord
    recommendations: List[InventoryRecommendation]


class PricingAgentRunResponse(BaseModel):
    run: AgentRunRecord
    recommendations: List[PricingRecommendation]


class CustomerInsightAgentRunResponse(BaseModel):
    run: AgentRunRecord
    report: CustomerInsightReport


class MarketingAgentRunResponse(BaseModel):
    run: AgentRunRecord
    drafts: List[MarketingDraft]


class DailyOpsRunRequest(BaseModel):
    run_id: Optional[str] = None
    workflow_run_id: Optional[str] = None
    triggered_by: str = "manual"
    lookback_days: int = Field(default=30, ge=1, le=365)
    channels: List[MarketingChannel] = Field(default_factory=lambda: [MarketingChannel.email])


class WorkflowStartResponse(BaseModel):
    workflow_id: str
    run_id: str
    task_queue: str
    runtime: str
    status: str


class InventoryUpdateRequest(BaseModel):
    warehouse: str
    available_stock: int = Field(ge=0)
    reserved_stock: int = Field(default=0, ge=0)
    reorder_point: int = Field(ge=0)
    supplier_lead_time_days: int = Field(ge=0)
    safety_stock: int = Field(ge=0)
    status: StockStatus


class DailyOpsReport(BaseModel):
    report_date: date
    inventory_alerts: List[InventoryRecommendation] = Field(default_factory=list)
    pricing_recommendations: List[PricingRecommendation] = Field(default_factory=list)
    marketing_drafts: List[MarketingDraft] = Field(default_factory=list)
    customer_issues: List[IssueCluster] = Field(default_factory=list)
    approvals_required: List[ApprovalRequest] = Field(default_factory=list)
    actions_completed: List[str] = Field(default_factory=list)
    actions_blocked: List[str] = Field(default_factory=list)
    executive_summary: str


class DailyOpsRunResponse(BaseModel):
    run: AgentRunRecord
    report: DailyOpsReport
