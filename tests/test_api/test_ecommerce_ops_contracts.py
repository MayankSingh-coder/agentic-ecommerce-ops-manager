from datetime import date, datetime, timezone

import pytest
from pydantic import ValidationError

from app.ecommerce_ops.contracts import (
    AgentContext,
    AgentName,
    ApprovalRequest,
    CustomerInsightReport,
    DailyOpsReport,
    InventoryAgentInput,
    InventoryRecommendation,
    IssueCluster,
    MarketingChannel,
    MarketingDraft,
    PolicyDecision,
    PricingRecommendation,
    RiskLevel,
)
from app.ecommerce_ops.repository import EcommerceOpsRepository


def test_inventory_agent_input_accepts_seed_operational_data():
    repository = EcommerceOpsRepository()
    context = AgentContext(
        run_id="run-001",
        prompt_version="inventory_agent_v1",
        created_at=datetime.now(timezone.utc),
    )

    payload = InventoryAgentInput(
        context=context,
        products=repository.list_products(),
        inventory=repository.list_inventory(),
        orders=repository.list_orders(),
        lookback_days=30,
    )

    assert payload.context.run_id == "run-001"
    assert len(payload.products) == 3
    assert payload.lookback_days == 30


def test_inventory_agent_input_rejects_invalid_lookback_window():
    repository = EcommerceOpsRepository()
    context = AgentContext(
        run_id="run-002",
        prompt_version="inventory_agent_v1",
        created_at=datetime.now(timezone.utc),
    )

    with pytest.raises(ValidationError):
        InventoryAgentInput(
            context=context,
            products=repository.list_products(),
            inventory=repository.list_inventory(),
            orders=repository.list_orders(),
            lookback_days=0,
        )


def test_pricing_recommendation_requires_approval_for_approval_policy():
    with pytest.raises(ValidationError, match="requires_approval"):
        PricingRecommendation(
            sku="SKU-1001",
            current_price=1499,
            recommended_price=1399,
            current_margin_pct=39.29,
            recommended_margin_pct=34.95,
            price_change_pct=-6.67,
            competitor_reference_price=1399,
            expected_revenue_impact=42000,
            confidence=0.82,
            risk_level=RiskLevel.medium,
            reason="Competitor price is lower and demand softened.",
            policy_decision=PolicyDecision.approval_required,
            requires_approval=False,
        )


def test_marketing_draft_blocks_high_risk_campaigns_without_reason():
    with pytest.raises(ValidationError, match="blocked_reason"):
        MarketingDraft(
            campaign_name="Critical stock promo",
            target_skus=["SKU-1002"],
            channel=MarketingChannel.email,
            audience_segment="low-engagement customers",
            subject_lines=["Limited offer"],
            body="Try this product today.",
            risk_level=RiskLevel.high,
            requires_approval=True,
        )


def test_daily_ops_report_combines_typed_agent_outputs():
    inventory_alert = InventoryRecommendation(
        sku="SKU-1002",
        warehouse="BLR-01",
        available_stock=12,
        avg_daily_sales=4,
        days_of_inventory=3,
        reorder_needed=True,
        recommended_reorder_qty=120,
        risk_level=RiskLevel.high,
        reason="Stock will fall below lead-time coverage.",
    )
    issue = IssueCluster(
        sku="SKU-1002",
        issue="Battery drain",
        review_count=12,
        return_count=6,
        representative_evidence=["Battery does not last as advertised."],
        severity=RiskLevel.high,
    )
    customer_report = CustomerInsightReport(
        clusters=[issue],
        summary="Battery complaints are concentrated on SKU-1002.",
    )
    approval = ApprovalRequest(
        approval_id="apr-001",
        run_id="run-003",
        agent_name=AgentName.marketing,
        resource_type="campaign_draft",
        resource_id="draft-001",
        reason="High-risk campaign requires human approval.",
        risk_level=RiskLevel.high,
        created_at=datetime.now(timezone.utc),
    )

    report = DailyOpsReport(
        report_date=date(2026, 5, 19),
        inventory_alerts=[inventory_alert],
        customer_issues=customer_report.clusters,
        approvals_required=[approval],
        actions_blocked=["Blocked campaign for SKU-1002 until approval."],
        executive_summary="SKU-1002 needs inventory and quality attention.",
    )

    assert report.report_date.isoformat() == "2026-05-19"
    assert report.inventory_alerts[0].sku == "SKU-1002"
    assert report.customer_issues[0].issue == "Battery drain"
    assert report.approvals_required[0].agent_name == AgentName.marketing
