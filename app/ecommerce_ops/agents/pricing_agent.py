from collections import defaultdict
from datetime import datetime, timezone
from typing import Dict, List, Optional

from ..contracts import (
    AgentName,
    AgentRunRecord,
    AgentRunStatus,
    PolicyDecision,
    PricingAgentInput,
    PricingRecommendation,
)
from ..policies.pricing_policy import PricingPolicyEngine
from ..schemas import CompetitorPrice, InventoryItem, Product


class PricingAgent:
    name = AgentName.pricing
    prompt_version = "pricing_agent_rules_v1"
    input_schema = "PricingAgentInput.v1"
    output_schema = "List[PricingRecommendation].v1"

    def __init__(self, policy_engine: PricingPolicyEngine | None = None) -> None:
        self.policy_engine = policy_engine or PricingPolicyEngine()

    def run(self, payload: PricingAgentInput) -> tuple[List[PricingRecommendation], AgentRunRecord]:
        started_at = datetime.now(timezone.utc)
        inventory_by_sku = {item.sku: item for item in payload.inventory}
        competitor_by_sku = self._best_competitor_prices(payload.competitor_prices)
        sales_velocity = self._sales_velocity(payload)

        recommendations = [
            self._build_recommendation(
                product=product,
                competitor=competitor_by_sku.get(product.sku),
                inventory_item=inventory_by_sku.get(product.sku),
                avg_daily_sales=sales_velocity[product.sku],
                reference_time=payload.context.created_at,
            )
            for product in payload.products
            if product.sku in competitor_by_sku
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
        return recommendations, run_record

    def _build_recommendation(
        self,
        *,
        product: Product,
        competitor: CompetitorPrice | None,
        inventory_item: InventoryItem | None,
        avg_daily_sales: float,
        reference_time: datetime,
    ) -> PricingRecommendation:
        current_price = product.price
        proposed_price = self._proposed_price(current_price, competitor)
        current_margin_pct = self._margin_pct(current_price, product.cost)
        proposed_margin_pct = self._margin_pct(proposed_price, product.cost)
        expected_revenue_impact = round((proposed_price - current_price) * avg_daily_sales * 30, 2)

        policy_result = self.policy_engine.evaluate(
            current_price=current_price,
            recommended_price=proposed_price,
            recommended_margin_pct=proposed_margin_pct,
            competitor_confidence=competitor.confidence if competitor else None,
            competitor_observed_at=competitor.observed_at if competitor else None,
            inventory_item=inventory_item,
            expected_revenue_impact=expected_revenue_impact,
            reference_time=reference_time,
        )

        if policy_result.decision == PolicyDecision.blocked:
            recommended_price = current_price
            recommended_margin_pct = current_margin_pct
            expected_revenue_impact = 0.0
        else:
            recommended_price = proposed_price
            recommended_margin_pct = proposed_margin_pct

        price_change_pct = round((recommended_price - current_price) / current_price * 100, 2)

        return PricingRecommendation(
            sku=product.sku,
            current_price=current_price,
            recommended_price=recommended_price,
            current_margin_pct=current_margin_pct,
            recommended_margin_pct=recommended_margin_pct,
            price_change_pct=price_change_pct,
            competitor_reference_price=competitor.price if competitor else None,
            expected_revenue_impact=expected_revenue_impact,
            confidence=competitor.confidence if competitor else 0,
            risk_level=policy_result.risk_level,
            reason=self._reason(product, competitor, policy_result.reason),
            policy_decision=policy_result.decision,
            requires_approval=policy_result.requires_approval,
        )

    def _best_competitor_prices(
        self,
        competitor_prices: List[CompetitorPrice],
    ) -> Dict[str, CompetitorPrice]:
        best_by_sku: Dict[str, CompetitorPrice] = {}
        for price in competitor_prices:
            current = best_by_sku.get(price.sku)
            if current is None or price.confidence > current.confidence:
                best_by_sku[price.sku] = price
        return best_by_sku

    def _sales_velocity(self, payload: PricingAgentInput) -> Dict[str, float]:
        quantities_by_sku: Dict[str, int] = defaultdict(int)
        for order in payload.orders:
            for item in order.items:
                quantities_by_sku[item.sku] += item.quantity

        return {
            product.sku: round(quantities_by_sku[product.sku] / 30, 2)
            for product in payload.products
        }

    def _proposed_price(
        self,
        current_price: float,
        competitor: Optional[CompetitorPrice],
    ) -> float:
        if competitor is None:
            return current_price
        if competitor.price < current_price:
            return round(max(competitor.price, current_price * 0.9), 2)
        if competitor.price > current_price * 1.05:
            return round(min(competitor.price * 0.98, current_price * 1.05), 2)
        return current_price

    def _margin_pct(self, price: float, cost: float) -> float:
        return round((price - cost) / price * 100, 2)

    def _reason(
        self,
        product: Product,
        competitor: CompetitorPrice | None,
        policy_reason: str,
    ) -> str:
        if competitor is None:
            return f"No competitor reference found for {product.sku}. {policy_reason}"
        return (
            f"Competitor {competitor.competitor} observed {product.sku} at "
            f"{competitor.price}. {policy_reason}"
        )
