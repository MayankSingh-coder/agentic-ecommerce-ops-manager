from datetime import datetime, timezone
from typing import Dict, List

from ..contracts import (
    AgentName,
    AgentRunRecord,
    AgentRunStatus,
    CustomerInsightReport,
    InventoryRecommendation,
    MarketingAgentInput,
    MarketingChannel,
    MarketingDraft,
    RiskLevel,
)
from ..schemas import Product
from app.llm.gateway import LLMGateway


class MarketingAgent:
    name = AgentName.marketing
    prompt_version = "marketing_agent_rules_v1"
    input_schema = "MarketingAgentInput.v1"
    output_schema = "List[MarketingDraft].v1"

    def __init__(self, llm_gateway: LLMGateway | None = None) -> None:
        self.llm_gateway = llm_gateway or LLMGateway()

    def run(self, payload: MarketingAgentInput) -> tuple[List[MarketingDraft], AgentRunRecord]:
        started_at = datetime.now(timezone.utc)
        products_by_sku = {product.sku: product for product in payload.products}
        inventory_by_sku = {
            recommendation.sku: recommendation
            for recommendation in payload.inventory_recommendations
        }
        issue_severity_by_sku = self._issue_severity_by_sku(payload.customer_insights)

        drafts = [
            draft
            for product in payload.products
            for draft in self._draft_for_product(
                product=product,
                inventory=inventory_by_sku.get(product.sku),
                issue_severity=issue_severity_by_sku.get(product.sku),
                channels=payload.channels,
            )
            if product.sku in products_by_sku
        ]
        completed_at = datetime.now(timezone.utc)
        run_record = AgentRunRecord(
            run_id=payload.context.run_id,
            agent_name=self.name,
            status=AgentRunStatus.succeeded,
            prompt_version=self.prompt_version,
            input_schema=self.input_schema,
            output_schema=self.output_schema,
            started_at=started_at,
            completed_at=completed_at,
        )
        return drafts, run_record

    def _draft_for_product(
        self,
        *,
        product: Product,
        inventory: InventoryRecommendation | None,
        issue_severity: RiskLevel | None,
        channels: List[MarketingChannel],
    ) -> List[MarketingDraft]:
        drafts = []
        for channel in channels:
            drafts.append(
                self._draft_for_channel(
                    product=product,
                    inventory=inventory,
                    issue_severity=issue_severity,
                    channel=channel,
                )
            )
        return drafts

    def _draft_for_channel(
        self,
        *,
        product: Product,
        inventory: InventoryRecommendation | None,
        issue_severity: RiskLevel | None,
        channel: MarketingChannel,
    ) -> MarketingDraft:
        if inventory and inventory.risk_level in {RiskLevel.high, RiskLevel.critical}:
            return MarketingDraft(
                campaign_name=f"Blocked campaign for {product.name}",
                target_skus=[product.sku],
                channel=channel,
                audience_segment="promotion-eligible customers",
                subject_lines=[],
                body="",
                offer=None,
                risk_level=RiskLevel.high,
                requires_approval=True,
                blocked_reason="Campaign blocked because product has high stockout risk.",
            )

        if issue_severity in {RiskLevel.high, RiskLevel.critical}:
            return MarketingDraft(
                campaign_name=f"Blocked campaign for {product.name}",
                target_skus=[product.sku],
                channel=channel,
                audience_segment="promotion-eligible customers",
                subject_lines=[],
                body="",
                offer=None,
                risk_level=RiskLevel.high,
                requires_approval=True,
                blocked_reason="Campaign blocked because unresolved product quality issues are high severity.",
            )

        return MarketingDraft(
            campaign_name=f"{product.category} recovery campaign - {product.sku}",
            target_skus=[product.sku],
            channel=channel,
            audience_segment=f"{product.category.lower()} browsers with no purchase in 30 days",
            subject_lines=[
                f"Still considering {product.name}?",
                f"A fresh offer on {product.brand}",
            ],
            body=(
                self.llm_gateway.generate_text(
                    prompt_id="marketing_draft_v1",
                    agent=self.name.value,
                    input_data={
                        "product_name": product.name,
                        "offer": "10% off",
                    },
                ).output
            ),
            offer="10% off",
            risk_level=RiskLevel.medium,
            requires_approval=True,
        )

    def _issue_severity_by_sku(self, report: CustomerInsightReport) -> Dict[str, RiskLevel]:
        severity_rank = {
            RiskLevel.low: 1,
            RiskLevel.medium: 2,
            RiskLevel.high: 3,
            RiskLevel.critical: 4,
        }
        severities: Dict[str, RiskLevel] = {}
        for cluster in report.clusters:
            current = severities.get(cluster.sku)
            if current is None or severity_rank[cluster.severity] > severity_rank[current]:
                severities[cluster.sku] = cluster.severity
        return severities
