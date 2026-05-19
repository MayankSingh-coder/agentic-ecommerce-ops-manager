import json
from datetime import datetime, timezone
from typing import List

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models import (
    AgentOutputModel,
    AgentRunModel,
    ApprovalRequestModel,
    AuditLogModel,
    CompetitorPriceModel,
    InventoryItemModel,
    OrderModel,
    ProductModel,
    ProductReturnModel,
    ReviewModel,
)
from app.ecommerce_ops.contracts import AgentName, AgentRunRecord, ApprovalRequest, ApprovalStatus, AuditLogEntry, RiskLevel
from app.ecommerce_ops.schemas import (
    CompetitorPrice,
    InventoryItem,
    Order,
    OrderItem,
    Product,
    ProductReturn,
    ReturnReason,
    Review,
    StockStatus,
)


class SqlAlchemyEcommerceOpsRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list_products(self) -> List[Product]:
        rows = self.session.scalars(select(ProductModel).order_by(ProductModel.sku)).all()
        return [
            Product(
                sku=row.sku,
                name=row.name,
                category=row.category,
                brand=row.brand,
                price=row.price,
                cost=row.cost,
                active=row.active,
            )
            for row in rows
        ]

    def list_inventory(self) -> List[InventoryItem]:
        rows = self.session.scalars(
            select(InventoryItemModel).order_by(InventoryItemModel.sku, InventoryItemModel.warehouse)
        ).all()
        return [
            InventoryItem(
                sku=row.sku,
                warehouse=row.warehouse,
                available_stock=row.available_stock,
                reserved_stock=row.reserved_stock,
                reorder_point=row.reorder_point,
                supplier_lead_time_days=row.supplier_lead_time_days,
                safety_stock=row.safety_stock,
                status=StockStatus(row.status),
            )
            for row in rows
        ]

    def list_orders(self) -> List[Order]:
        rows = self.session.scalars(select(OrderModel).order_by(OrderModel.order_id)).unique().all()
        return [
            Order(
                order_id=row.order_id,
                customer_id=row.customer_id,
                items=[
                    OrderItem(
                        sku=item.sku,
                        quantity=item.quantity,
                        unit_price=item.unit_price,
                    )
                    for item in row.items
                ],
                total_amount=row.total_amount,
                created_at=self._as_utc(row.created_at),
            )
            for row in rows
        ]

    def list_returns(self) -> List[ProductReturn]:
        rows = self.session.scalars(select(ProductReturnModel).order_by(ProductReturnModel.return_id)).all()
        return [
            ProductReturn(
                return_id=row.return_id,
                order_id=row.order_id,
                sku=row.sku,
                reason=ReturnReason(row.reason),
                notes=row.notes,
                created_at=self._as_utc(row.created_at),
            )
            for row in rows
        ]

    def list_reviews(self) -> List[Review]:
        rows = self.session.scalars(select(ReviewModel).order_by(ReviewModel.review_id)).all()
        return [
            Review(
                review_id=row.review_id,
                sku=row.sku,
                rating=row.rating,
                title=row.title,
                body=row.body,
                created_at=self._as_utc(row.created_at),
            )
            for row in rows
        ]

    def list_competitors(self) -> List[CompetitorPrice]:
        rows = self.session.scalars(
            select(CompetitorPriceModel).order_by(CompetitorPriceModel.sku, CompetitorPriceModel.competitor)
        ).all()
        return [
            CompetitorPrice(
                sku=row.sku,
                competitor=row.competitor,
                price=row.price,
                product_url=row.product_url,
                observed_at=self._as_utc(row.observed_at),
                confidence=row.confidence,
            )
            for row in rows
        ]

    def upsert_inventory_item(self, item: InventoryItem) -> InventoryItem:
        product = self.session.get(ProductModel, item.sku)
        if product is None:
            raise ValueError(f"Unknown product SKU: {item.sku}")
        row = self.session.scalar(
            select(InventoryItemModel).where(
                InventoryItemModel.sku == item.sku,
                InventoryItemModel.warehouse == item.warehouse,
            )
        )
        if row is None:
            row = InventoryItemModel(sku=item.sku, warehouse=item.warehouse)
            self.session.add(row)
        row.available_stock = item.available_stock
        row.reserved_stock = item.reserved_stock
        row.reorder_point = item.reorder_point
        row.supplier_lead_time_days = item.supplier_lead_time_days
        row.safety_stock = item.safety_stock
        row.status = item.status.value
        self.session.commit()
        return item

    def add_review(self, review: Review) -> Review:
        product = self.session.get(ProductModel, review.sku)
        if product is None:
            raise ValueError(f"Unknown product SKU: {review.sku}")
        self.session.merge(
            ReviewModel(
                review_id=review.review_id,
                sku=review.sku,
                rating=review.rating,
                title=review.title,
                body=review.body,
                created_at=review.created_at,
            )
        )
        self.session.commit()
        return review

    def add_return(self, product_return: ProductReturn) -> ProductReturn:
        product = self.session.get(ProductModel, product_return.sku)
        order = self.session.get(OrderModel, product_return.order_id)
        if product is None:
            raise ValueError(f"Unknown product SKU: {product_return.sku}")
        if order is None:
            raise ValueError(f"Unknown order ID: {product_return.order_id}")
        self.session.merge(
            ProductReturnModel(
                return_id=product_return.return_id,
                order_id=product_return.order_id,
                sku=product_return.sku,
                reason=product_return.reason.value,
                notes=product_return.notes,
                created_at=product_return.created_at,
            )
        )
        self.session.commit()
        return product_return

    def add_competitor_price(self, competitor_price: CompetitorPrice) -> CompetitorPrice:
        product = self.session.get(ProductModel, competitor_price.sku)
        if product is None:
            raise ValueError(f"Unknown product SKU: {competitor_price.sku}")
        self.session.add(
            CompetitorPriceModel(
                sku=competitor_price.sku,
                competitor=competitor_price.competitor,
                price=competitor_price.price,
                product_url=competitor_price.product_url,
                observed_at=competitor_price.observed_at,
                confidence=competitor_price.confidence,
            )
        )
        self.session.commit()
        return competitor_price

    def save_agent_run(self, run_record: AgentRunRecord, output_type: str, payload: object) -> None:
        agent_run = self.session.scalar(
            select(AgentRunModel).where(
                AgentRunModel.run_id == run_record.run_id,
                AgentRunModel.agent_name == run_record.agent_name.value,
            )
        )
        if agent_run is None:
            agent_run = AgentRunModel(
                run_id=run_record.run_id,
                agent_name=run_record.agent_name.value,
            )
            self.session.add(agent_run)
        agent_run.status = run_record.status.value
        agent_run.prompt_version = run_record.prompt_version
        agent_run.input_schema = run_record.input_schema
        agent_run.output_schema = run_record.output_schema
        agent_run.started_at = run_record.started_at
        agent_run.completed_at = run_record.completed_at
        agent_run.error_message = run_record.error_message
        self.session.flush()
        self.session.add(
            AgentOutputModel(
                agent_run_id=agent_run.id,
                run_id=run_record.run_id,
                output_type=output_type,
                payload_json=self._json_payload(payload),
                created_at=datetime.now(timezone.utc),
            )
        )
        self.session.commit()

    def count_agent_runs(self) -> int:
        return len(self.session.scalars(select(AgentRunModel.id)).all())

    def list_agent_outputs(self, run_id: str) -> List[str]:
        return self.session.scalars(
            select(AgentOutputModel.payload_json).where(AgentOutputModel.run_id == run_id)
        ).all()

    def create_approval_request(self, approval: ApprovalRequest) -> None:
        self.session.merge(
            ApprovalRequestModel(
                approval_id=approval.approval_id,
                run_id=approval.run_id,
                agent_name=approval.agent_name.value,
                resource_type=approval.resource_type,
                resource_id=approval.resource_id,
                reason=approval.reason,
                risk_level=approval.risk_level.value,
                status=approval.status.value,
                created_at=approval.created_at,
                decided_at=approval.decided_at,
                decided_by=approval.decided_by,
            )
        )
        self.session.commit()

    def list_approval_requests(self) -> List[ApprovalRequest]:
        rows = self.session.scalars(
            select(ApprovalRequestModel).order_by(ApprovalRequestModel.created_at, ApprovalRequestModel.approval_id)
        ).all()
        return [self._approval_from_model(row) for row in rows]

    def get_approval_request(self, approval_id: str) -> ApprovalRequest | None:
        row = self.session.get(ApprovalRequestModel, approval_id)
        if row is None:
            return None
        return self._approval_from_model(row)

    def update_approval_status(
        self,
        approval_id: str,
        status: ApprovalStatus,
        decided_by: str,
        decided_at: datetime,
    ) -> ApprovalRequest | None:
        row = self.session.get(ApprovalRequestModel, approval_id)
        if row is None:
            return None
        row.status = status.value
        row.decided_by = decided_by
        row.decided_at = decided_at
        self.session.commit()
        self.session.refresh(row)
        return self._approval_from_model(row)

    def create_audit_log(self, entry: AuditLogEntry) -> AuditLogEntry:
        row = AuditLogModel(
            actor=entry.actor,
            action=entry.action,
            resource_type=entry.resource_type,
            resource_id=entry.resource_id,
            payload_json=json.dumps(entry.payload),
            created_at=entry.created_at,
        )
        self.session.add(row)
        self.session.commit()
        self.session.refresh(row)
        return self._audit_log_from_model(row)

    def list_audit_logs(self, run_id: str | None = None) -> List[AuditLogEntry]:
        rows = self.session.scalars(
            select(AuditLogModel).order_by(AuditLogModel.created_at, AuditLogModel.id)
        ).all()
        entries = [self._audit_log_from_model(row) for row in rows]
        if run_id is None:
            return entries
        return [
            entry
            for entry in entries
            if entry.payload.get("run_id") == run_id or entry.resource_id == run_id
        ]

    def _json_payload(self, payload: object) -> str:
        if hasattr(payload, "model_dump"):
            return json.dumps(payload.model_dump(mode="json"))
        if isinstance(payload, list):
            return json.dumps([
                item.model_dump(mode="json") if hasattr(item, "model_dump") else item
                for item in payload
            ])
        return json.dumps(payload)

    def _as_utc(self, value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    def _approval_from_model(self, row: ApprovalRequestModel) -> ApprovalRequest:
        return ApprovalRequest(
            approval_id=row.approval_id,
            run_id=row.run_id,
            agent_name=AgentName(row.agent_name),
            resource_type=row.resource_type,
            resource_id=row.resource_id,
            reason=row.reason,
            risk_level=RiskLevel(row.risk_level),
            status=ApprovalStatus(row.status),
            created_at=self._as_utc(row.created_at),
            decided_at=self._as_utc(row.decided_at) if row.decided_at else None,
            decided_by=row.decided_by,
        )

    def _audit_log_from_model(self, row: AuditLogModel) -> AuditLogEntry:
        payload = json.loads(row.payload_json) if row.payload_json else {}
        return AuditLogEntry(
            audit_id=row.id,
            actor=row.actor,
            action=row.action,
            resource_type=row.resource_type,
            resource_id=row.resource_id,
            payload=payload,
            created_at=self._as_utc(row.created_at),
        )
