"""initial schema

Revision ID: 0001_initial_schema
Revises: 
Create Date: 2026-05-19
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0001_initial_schema"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "products",
        sa.Column("sku", sa.String(length=64), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("category", sa.String(length=120), nullable=False),
        sa.Column("brand", sa.String(length=120), nullable=False),
        sa.Column("price", sa.Float(), nullable=False),
        sa.Column("cost", sa.Float(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
    )
    op.create_table(
        "orders",
        sa.Column("order_id", sa.String(length=64), primary_key=True),
        sa.Column("customer_id", sa.String(length=64), nullable=False),
        sa.Column("total_amount", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "agent_runs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("run_id", sa.String(length=120), nullable=False),
        sa.Column("agent_name", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("prompt_version", sa.String(length=120), nullable=False),
        sa.Column("input_schema", sa.String(length=120), nullable=False),
        sa.Column("output_schema", sa.String(length=120), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.UniqueConstraint("run_id", "agent_name", name="uq_agent_runs_run_id_agent_name"),
    )
    op.create_index("ix_agent_runs_run_id", "agent_runs", ["run_id"])
    op.create_index("ix_agent_runs_agent_name", "agent_runs", ["agent_name"])
    op.create_table(
        "inventory_items",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("sku", sa.String(length=64), sa.ForeignKey("products.sku"), nullable=False),
        sa.Column("warehouse", sa.String(length=64), nullable=False),
        sa.Column("available_stock", sa.Integer(), nullable=False),
        sa.Column("reserved_stock", sa.Integer(), nullable=False),
        sa.Column("reorder_point", sa.Integer(), nullable=False),
        sa.Column("supplier_lead_time_days", sa.Integer(), nullable=False),
        sa.Column("safety_stock", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
    )
    op.create_index("ix_inventory_items_sku", "inventory_items", ["sku"])
    op.create_table(
        "order_items",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("order_id", sa.String(length=64), sa.ForeignKey("orders.order_id"), nullable=False),
        sa.Column("sku", sa.String(length=64), sa.ForeignKey("products.sku"), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("unit_price", sa.Float(), nullable=False),
    )
    op.create_index("ix_order_items_order_id", "order_items", ["order_id"])
    op.create_index("ix_order_items_sku", "order_items", ["sku"])
    op.create_table(
        "returns",
        sa.Column("return_id", sa.String(length=64), primary_key=True),
        sa.Column("order_id", sa.String(length=64), sa.ForeignKey("orders.order_id"), nullable=False),
        sa.Column("sku", sa.String(length=64), sa.ForeignKey("products.sku"), nullable=False),
        sa.Column("reason", sa.String(length=64), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_returns_order_id", "returns", ["order_id"])
    op.create_index("ix_returns_sku", "returns", ["sku"])
    op.create_table(
        "reviews",
        sa.Column("review_id", sa.String(length=64), primary_key=True),
        sa.Column("sku", sa.String(length=64), sa.ForeignKey("products.sku"), nullable=False),
        sa.Column("rating", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_reviews_sku", "reviews", ["sku"])
    op.create_table(
        "competitor_prices",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("sku", sa.String(length=64), sa.ForeignKey("products.sku"), nullable=False),
        sa.Column("competitor", sa.String(length=120), nullable=False),
        sa.Column("price", sa.Float(), nullable=False),
        sa.Column("product_url", sa.String(length=500), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
    )
    op.create_index("ix_competitor_prices_sku", "competitor_prices", ["sku"])
    op.create_table(
        "agent_outputs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("agent_run_id", sa.Integer(), sa.ForeignKey("agent_runs.id"), nullable=False),
        sa.Column("run_id", sa.String(length=120), nullable=False),
        sa.Column("output_type", sa.String(length=120), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_agent_outputs_agent_run_id", "agent_outputs", ["agent_run_id"])
    op.create_index("ix_agent_outputs_run_id", "agent_outputs", ["run_id"])
    op.create_table(
        "approval_requests",
        sa.Column("approval_id", sa.String(length=120), primary_key=True),
        sa.Column("run_id", sa.String(length=120), nullable=False),
        sa.Column("agent_name", sa.String(length=64), nullable=False),
        sa.Column("resource_type", sa.String(length=120), nullable=False),
        sa.Column("resource_id", sa.String(length=120), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("risk_level", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decided_by", sa.String(length=120), nullable=True),
    )
    op.create_index("ix_approval_requests_run_id", "approval_requests", ["run_id"])
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("actor", sa.String(length=120), nullable=False),
        sa.Column("action", sa.String(length=120), nullable=False),
        sa.Column("resource_type", sa.String(length=120), nullable=False),
        sa.Column("resource_id", sa.String(length=120), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("audit_logs")
    op.drop_index("ix_approval_requests_run_id", table_name="approval_requests")
    op.drop_table("approval_requests")
    op.drop_index("ix_agent_outputs_run_id", table_name="agent_outputs")
    op.drop_table("agent_outputs")
    op.drop_index("ix_competitor_prices_sku", table_name="competitor_prices")
    op.drop_table("competitor_prices")
    op.drop_index("ix_reviews_sku", table_name="reviews")
    op.drop_table("reviews")
    op.drop_index("ix_returns_sku", table_name="returns")
    op.drop_index("ix_returns_order_id", table_name="returns")
    op.drop_table("returns")
    op.drop_index("ix_order_items_sku", table_name="order_items")
    op.drop_index("ix_order_items_order_id", table_name="order_items")
    op.drop_table("order_items")
    op.drop_index("ix_inventory_items_sku", table_name="inventory_items")
    op.drop_table("inventory_items")
    op.drop_index("ix_agent_runs_agent_name", table_name="agent_runs")
    op.drop_index("ix_agent_runs_run_id", table_name="agent_runs")
    op.drop_table("agent_runs")
    op.drop_table("orders")
    op.drop_table("products")
