from collections import defaultdict
from datetime import datetime, timezone
from math import ceil
from typing import Dict, List

from ..contracts import (
    AgentName,
    AgentRunRecord,
    AgentRunStatus,
    InventoryAgentInput,
    InventoryRecommendation,
    RiskLevel,
)


class InventoryAgent:
    name = AgentName.inventory
    prompt_version = "inventory_agent_rules_v1"
    input_schema = "InventoryAgentInput.v1"
    output_schema = "List[InventoryRecommendation].v1"

    def run(self, payload: InventoryAgentInput) -> tuple[List[InventoryRecommendation], AgentRunRecord]:
        started_at = datetime.now(timezone.utc)
        recommendations = [
            self._build_recommendation(item, self._sales_velocity(payload)[item.sku])
            for item in payload.inventory
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

    def _sales_velocity(self, payload: InventoryAgentInput) -> Dict[str, float]:
        quantities_by_sku: Dict[str, int] = defaultdict(int)
        for order in payload.orders:
            for item in order.items:
                quantities_by_sku[item.sku] += item.quantity

        return {
            product.sku: round(quantities_by_sku[product.sku] / payload.lookback_days, 2)
            for product in payload.products
        }

    def _build_recommendation(
        self,
        item,
        avg_daily_sales: float,
    ) -> InventoryRecommendation:
        available_to_sell = max(item.available_stock - item.reserved_stock, 0)
        days_of_inventory = None
        if avg_daily_sales > 0:
            days_of_inventory = round(available_to_sell / avg_daily_sales, 2)

        projected_stock_after_lead_time = available_to_sell - (
            avg_daily_sales * item.supplier_lead_time_days
        )
        reorder_needed = (
            available_to_sell <= item.reorder_point
            or projected_stock_after_lead_time < item.safety_stock
        )
        recommended_reorder_qty = self._recommended_reorder_quantity(
            available_to_sell=available_to_sell,
            avg_daily_sales=avg_daily_sales,
            supplier_lead_time_days=item.supplier_lead_time_days,
            safety_stock=item.safety_stock,
            reorder_point=item.reorder_point,
            reorder_needed=reorder_needed,
        )
        risk_level = self._risk_level(
            available_to_sell=available_to_sell,
            days_of_inventory=days_of_inventory,
            projected_stock_after_lead_time=projected_stock_after_lead_time,
            safety_stock=item.safety_stock,
            reorder_needed=reorder_needed,
        )

        return InventoryRecommendation(
            sku=item.sku,
            warehouse=item.warehouse,
            available_stock=item.available_stock,
            avg_daily_sales=avg_daily_sales,
            days_of_inventory=days_of_inventory,
            reorder_needed=reorder_needed,
            recommended_reorder_qty=recommended_reorder_qty,
            risk_level=risk_level,
            reason=self._reason(
                available_to_sell=available_to_sell,
                reorder_point=item.reorder_point,
                days_of_inventory=days_of_inventory,
                projected_stock_after_lead_time=projected_stock_after_lead_time,
                safety_stock=item.safety_stock,
                reorder_needed=reorder_needed,
            ),
            requires_approval=False,
        )

    def _recommended_reorder_quantity(
        self,
        available_to_sell: int,
        avg_daily_sales: float,
        supplier_lead_time_days: int,
        safety_stock: int,
        reorder_point: int,
        reorder_needed: bool,
    ) -> int:
        if not reorder_needed:
            return 0

        lead_time_demand = avg_daily_sales * supplier_lead_time_days
        target_stock = max(lead_time_demand + safety_stock + reorder_point, reorder_point)
        return max(ceil(target_stock - available_to_sell), 0)

    def _risk_level(
        self,
        available_to_sell: int,
        days_of_inventory: float | None,
        projected_stock_after_lead_time: float,
        safety_stock: int,
        reorder_needed: bool,
    ) -> RiskLevel:
        if available_to_sell == 0:
            return RiskLevel.critical
        if projected_stock_after_lead_time <= 0:
            return RiskLevel.critical
        if projected_stock_after_lead_time < safety_stock:
            return RiskLevel.high
        if days_of_inventory is not None and days_of_inventory < 3:
            return RiskLevel.high
        if reorder_needed:
            return RiskLevel.medium
        return RiskLevel.low

    def _reason(
        self,
        available_to_sell: int,
        reorder_point: int,
        days_of_inventory: float | None,
        projected_stock_after_lead_time: float,
        safety_stock: int,
        reorder_needed: bool,
    ) -> str:
        if not reorder_needed:
            return "Inventory coverage is above reorder threshold."
        if days_of_inventory is None:
            return (
                f"Available-to-sell stock is {available_to_sell}, "
                f"which is at or below reorder point {reorder_point}."
            )
        return (
            f"Available-to-sell stock is {available_to_sell}; "
            f"estimated coverage is {days_of_inventory} days and projected "
            f"stock after lead time is {round(projected_stock_after_lead_time, 2)} "
            f"against safety stock {safety_stock}."
        )
