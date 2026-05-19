from datetime import datetime, timezone
from typing import List
from uuid import uuid4

from .agents.customer_insight_agent import CustomerInsightAgent
from .agents.inventory_agent import InventoryAgent
from .agents.marketing_agent import MarketingAgent
from .agents.pricing_agent import PricingAgent
from .contracts import (
    AgentContext,
    AgentName,
    AgentRunRecord,
    AgentRunStatus,
    ApprovalRequest,
    ApprovalStatus,
    AuditLogEntry,
    CustomerInsightAgentInput,
    CustomerInsightAgentRunResponse,
    DailyOpsReport,
    DailyOpsRunResponse,
    InventoryAgentInput,
    InventoryAgentRunResponse,
    MarketingAgentInput,
    MarketingAgentRunResponse,
    PricingAgentInput,
    PricingAgentRunResponse,
)
from .repository import EcommerceOpsRepository
from .schemas import (
    CompetitorPrice,
    InventoryItem,
    Order,
    Product,
    ProductReturn,
    Review,
)
from .workflows.daily_ops_graph import DailyOpsGraphWorkflow
from app.llm.gateway import LLMGateway
from app.llm.gateway_types import LLMGatewayResponse


class EcommerceOpsService:
    def __init__(self, repository: EcommerceOpsRepository, llm_gateway: LLMGateway | None = None) -> None:
        self.repository = repository
        self.llm_gateway = llm_gateway or LLMGateway()

    def health(self) -> dict:
        return {
            "service": "ecommerce-ops",
            "status": "healthy",
            "phase": "phase-20-interview-package",
        }

    def contract_registry(self) -> dict:
        return {
            "version": "v1",
            "phase": "phase-20-interview-package",
            "agent_inputs": [
                "InventoryAgentInput",
                "PricingAgentInput",
                "CustomerInsightAgentInput",
                "MarketingAgentInput",
            ],
            "agent_outputs": [
                "InventoryRecommendation",
                "PricingRecommendation",
                "CustomerInsightReport",
                "MarketingDraft",
            ],
            "control_contracts": [
                "ApprovalRequest",
                "ApprovalDecisionRequest",
                "AuditLogEntry",
                "AgentRunRecord",
                "DailyOpsReport",
                "DailyOpsRunResponse",
                "DailyOpsWorkflowState",
                "PromptConfig",
                "LLMGatewayResponse",
                "InMemoryLLMCache",
                "APIKeyAuth",
                "UntrustedTextSanitizer",
                "WorkflowStartResponse",
                "TemporalWorkflowRuntime",
                "DockerDeployment",
                "EvalSuite",
                "EvalSuiteResult",
                "InterviewPackage",
            ],
            "available_agent_runs": [
                "POST /api/v1/ecommerce-ops/workflows/daily-ops/run",
                "POST /api/v1/ecommerce-ops/workflows/daily-ops/temporal/start",
                "POST /api/v1/ecommerce-ops/agents/inventory/run",
                "POST /api/v1/ecommerce-ops/agents/pricing/run",
                "POST /api/v1/ecommerce-ops/agents/customer-insights/run",
                "POST /api/v1/ecommerce-ops/agents/marketing/run",
                "GET /api/v1/ecommerce-ops/db/products",
                "GET /api/v1/ecommerce-ops/approvals",
                "GET /api/v1/ecommerce-ops/observability/audit-logs",
                "POST /api/v1/ecommerce-ops/approvals/{approval_id}/approve",
                "POST /api/v1/ecommerce-ops/approvals/{approval_id}/reject",
                "PATCH /api/v1/ecommerce-ops/inventory/{sku}",
                "POST /api/v1/ecommerce-ops/reviews",
                "POST /api/v1/ecommerce-ops/returns",
                "POST /api/v1/ecommerce-ops/competitors",
            ],
        }

    def list_products(self) -> List[Product]:
        return self.repository.list_products()

    def list_inventory(self) -> List[InventoryItem]:
        return self.repository.list_inventory()

    def list_orders(self) -> List[Order]:
        return self.repository.list_orders()

    def list_returns(self) -> List[ProductReturn]:
        return self.repository.list_returns()

    def list_reviews(self) -> List[Review]:
        return self.repository.list_reviews()

    def list_competitors(self) -> List[CompetitorPrice]:
        return self.repository.list_competitors()

    def run_inventory_agent(
        self,
        context: AgentContext,
        lookback_days: int = 30,
    ) -> InventoryAgentRunResponse:
        agent = InventoryAgent()
        payload = InventoryAgentInput(
            context=context,
            products=self.repository.list_products(),
            inventory=self.repository.list_inventory(),
            orders=self.repository.list_orders(),
            lookback_days=lookback_days,
        )
        recommendations, run_record = agent.run(payload)
        self._persist_agent_output(
            run_record=run_record,
            output_type="inventory_recommendations",
            payload=recommendations,
        )
        return InventoryAgentRunResponse(
            run=run_record,
            recommendations=recommendations,
        )

    def run_pricing_agent(
        self,
        context: AgentContext,
    ) -> PricingAgentRunResponse:
        agent = PricingAgent()
        payload = PricingAgentInput(
            context=context,
            products=self.repository.list_products(),
            inventory=self.repository.list_inventory(),
            orders=self.repository.list_orders(),
            competitor_prices=self.repository.list_competitors(),
        )
        recommendations, run_record = agent.run(payload)
        self._persist_agent_output(
            run_record=run_record,
            output_type="pricing_recommendations",
            payload=recommendations,
        )
        self._create_pricing_approvals(run_record.run_id, recommendations)
        return PricingAgentRunResponse(
            run=run_record,
            recommendations=recommendations,
        )

    def run_customer_insight_agent(
        self,
        context: AgentContext,
        lookback_days: int = 30,
    ) -> CustomerInsightAgentRunResponse:
        agent = CustomerInsightAgent(llm_gateway=self.llm_gateway)
        payload = CustomerInsightAgentInput(
            context=context,
            products=self.repository.list_products(),
            reviews=self.repository.list_reviews(),
            returns=self.repository.list_returns(),
            lookback_days=lookback_days,
        )
        report, run_record = agent.run(payload)
        self._persist_agent_output(
            run_record=run_record,
            output_type="customer_insight_report",
            payload=report,
        )
        return CustomerInsightAgentRunResponse(
            run=run_record,
            report=report,
        )

    def run_marketing_agent(
        self,
        context: AgentContext,
        channels,
        inventory_recommendations=None,
        customer_insights=None,
        lookback_days: int = 30,
    ) -> MarketingAgentRunResponse:
        if inventory_recommendations is None:
            inventory_agent = InventoryAgent()
            inventory_payload = InventoryAgentInput(
                context=context,
                products=self.repository.list_products(),
                inventory=self.repository.list_inventory(),
                orders=self.repository.list_orders(),
                lookback_days=lookback_days,
            )
            inventory_recommendations, _ = inventory_agent.run(inventory_payload)

        if customer_insights is None:
            insight_agent = CustomerInsightAgent(llm_gateway=self.llm_gateway)
            insight_payload = CustomerInsightAgentInput(
                context=context,
                products=self.repository.list_products(),
                reviews=self.repository.list_reviews(),
                returns=self.repository.list_returns(),
                lookback_days=lookback_days,
            )
            customer_insights, _ = insight_agent.run(insight_payload)

        marketing_agent = MarketingAgent(llm_gateway=self.llm_gateway)
        marketing_payload = MarketingAgentInput(
            context=context,
            products=self.repository.list_products(),
            inventory_recommendations=inventory_recommendations,
            customer_insights=customer_insights,
            channels=channels,
        )
        drafts, run_record = marketing_agent.run(marketing_payload)
        self._persist_agent_output(
            run_record=run_record,
            output_type="marketing_drafts",
            payload=drafts,
        )
        self._create_marketing_approvals(run_record.run_id, drafts)
        return MarketingAgentRunResponse(
            run=run_record,
            drafts=drafts,
        )

    def run_daily_ops_workflow(
        self,
        context: AgentContext,
        lookback_days: int,
        channels,
    ) -> DailyOpsRunResponse:
        return DailyOpsGraphWorkflow().run(
            service=self,
            context=context,
            lookback_days=lookback_days,
            channels=channels,
        )

    def _persist_agent_output(self, run_record, output_type: str, payload: object) -> None:
        self.repository.save_agent_run(run_record, output_type, payload)

    def _create_pricing_approvals(self, run_id: str, recommendations) -> None:
        for recommendation in recommendations:
            if not recommendation.requires_approval:
                continue
            self.repository.create_approval_request(
                ApprovalRequest(
                    approval_id=f"apr-{uuid4()}",
                    run_id=run_id,
                    agent_name=AgentName.pricing,
                    resource_type="pricing_recommendation",
                    resource_id=recommendation.sku,
                    reason=recommendation.reason,
                    risk_level=recommendation.risk_level,
                    status=ApprovalStatus.pending,
                    created_at=datetime.now(timezone.utc),
                )
            )

    def _create_marketing_approvals(self, run_id: str, drafts) -> None:
        for draft in drafts:
            if not draft.requires_approval or draft.blocked_reason:
                continue
            self.repository.create_approval_request(
                ApprovalRequest(
                    approval_id=f"apr-{uuid4()}",
                    run_id=run_id,
                    agent_name=AgentName.marketing,
                    resource_type="marketing_draft",
                    resource_id=",".join(draft.target_skus),
                    reason="Marketing campaign draft requires approval before send.",
                    risk_level=draft.risk_level,
                    status=ApprovalStatus.pending,
                    created_at=datetime.now(timezone.utc),
                )
            )

    def list_approval_requests(self) -> List[ApprovalRequest]:
        return self.repository.list_approval_requests()

    def approve_request(self, approval_id: str, decided_by: str) -> ApprovalRequest | None:
        return self._decide_approval(
            approval_id=approval_id,
            status=ApprovalStatus.approved,
            decided_by=decided_by,
        )

    def reject_request(self, approval_id: str, decided_by: str) -> ApprovalRequest | None:
        return self._decide_approval(
            approval_id=approval_id,
            status=ApprovalStatus.rejected,
            decided_by=decided_by,
        )

    def _decide_approval(
        self,
        approval_id: str,
        status: ApprovalStatus,
        decided_by: str,
    ) -> ApprovalRequest | None:
        return self.repository.update_approval_status(
            approval_id=approval_id,
            status=status,
            decided_by=decided_by,
            decided_at=datetime.now(timezone.utc),
        )

    def record_audit_log(
        self,
        actor: str,
        action: str,
        resource_type: str,
        resource_id: str,
        payload: dict,
    ) -> AuditLogEntry | None:
        return self.repository.create_audit_log(
            AuditLogEntry(
                actor=actor,
                action=action,
                resource_type=resource_type,
                resource_id=resource_id,
                payload=payload,
                created_at=datetime.now(timezone.utc),
            )
        )

    def list_audit_logs(self, run_id: str | None = None) -> List[AuditLogEntry]:
        return self.repository.list_audit_logs(run_id=run_id)

    def _daily_completed_actions(self, inventory_count: int, pricing_count: int, marketing_count: int) -> List[str]:
        return [
            f"Evaluated {inventory_count} inventory records.",
            f"Generated {pricing_count} pricing recommendations.",
            f"Generated {marketing_count} marketing drafts.",
        ]

    def _daily_blocked_actions(self, marketing_drafts) -> List[str]:
        return [
            f"Blocked marketing draft for {', '.join(draft.target_skus)}: {draft.blocked_reason}"
            for draft in marketing_drafts
            if draft.blocked_reason
        ]
