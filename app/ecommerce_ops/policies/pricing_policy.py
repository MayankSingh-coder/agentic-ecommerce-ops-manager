from datetime import datetime
from typing import Optional

from ..contracts import PolicyDecision, RiskLevel
from ..schemas import InventoryItem


class PricingPolicyResult:
    def __init__(
        self,
        decision: PolicyDecision,
        risk_level: RiskLevel,
        requires_approval: bool,
        reason: str,
    ) -> None:
        self.decision = decision
        self.risk_level = risk_level
        self.requires_approval = requires_approval
        self.reason = reason


class PricingPolicyEngine:
    minimum_margin_pct = 22.0
    maximum_price_change_pct = 10.0
    approval_revenue_impact_threshold = 50000.0
    minimum_competitor_confidence = 0.8
    maximum_competitor_age_hours = 24.0

    def evaluate(
        self,
        *,
        current_price: float,
        recommended_price: float,
        recommended_margin_pct: float,
        competitor_confidence: Optional[float],
        competitor_observed_at: Optional[datetime],
        inventory_item: Optional[InventoryItem],
        expected_revenue_impact: float,
        reference_time: datetime,
    ) -> PricingPolicyResult:
        price_change_pct = abs((recommended_price - current_price) / current_price * 100)

        if recommended_margin_pct < self.minimum_margin_pct:
            return PricingPolicyResult(
                decision=PolicyDecision.blocked,
                risk_level=RiskLevel.critical,
                requires_approval=False,
                reason="Blocked because recommended price breaches minimum margin floor.",
            )

        if inventory_item and self._is_critical_stock(inventory_item) and recommended_price < current_price:
            return PricingPolicyResult(
                decision=PolicyDecision.blocked,
                risk_level=RiskLevel.high,
                requires_approval=False,
                reason="Blocked because discounting is not allowed on critical-stock SKUs.",
            )

        if price_change_pct > self.maximum_price_change_pct:
            return PricingPolicyResult(
                decision=PolicyDecision.approval_required,
                risk_level=RiskLevel.high,
                requires_approval=True,
                reason="Approval required because price movement exceeds daily threshold.",
            )

        if competitor_confidence is not None and competitor_confidence < self.minimum_competitor_confidence:
            return PricingPolicyResult(
                decision=PolicyDecision.approval_required,
                risk_level=RiskLevel.medium,
                requires_approval=True,
                reason="Approval required because competitor confidence is below threshold.",
            )

        if competitor_observed_at is not None:
            age_hours = max((reference_time - competitor_observed_at).total_seconds() / 3600, 0)
            if age_hours > self.maximum_competitor_age_hours:
                return PricingPolicyResult(
                    decision=PolicyDecision.approval_required,
                    risk_level=RiskLevel.medium,
                    requires_approval=True,
                    reason="Approval required because competitor price data is stale.",
                )

        if abs(expected_revenue_impact) > self.approval_revenue_impact_threshold:
            return PricingPolicyResult(
                decision=PolicyDecision.approval_required,
                risk_level=RiskLevel.medium,
                requires_approval=True,
                reason="Approval required because expected revenue impact exceeds threshold.",
            )

        return PricingPolicyResult(
            decision=PolicyDecision.allowed,
            risk_level=RiskLevel.low,
            requires_approval=False,
            reason="Allowed by pricing policy.",
        )

    def _is_critical_stock(self, inventory_item: InventoryItem) -> bool:
        available_to_sell = inventory_item.available_stock - inventory_item.reserved_stock
        return available_to_sell <= inventory_item.safety_stock
