from datetime import datetime, timezone
from typing import List

from .contracts import AgentRunRecord, ApprovalRequest, ApprovalStatus, AuditLogEntry
from .schemas import (
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


class EcommerceOpsRepository:
    """Phase 1 read repository backed by deterministic seed data."""

    def __init__(self) -> None:
        self._products = [
            Product(
                sku="SKU-1001",
                name="AeroFit Running Shoes",
                category="Footwear",
                brand="AeroFit",
                price=1499,
                cost=910,
            ),
            Product(
                sku="SKU-1002",
                name="VoltX Wireless Earbuds",
                category="Electronics",
                brand="VoltX",
                price=2299,
                cost=1320,
            ),
            Product(
                sku="SKU-1003",
                name="UrbanTrail Backpack",
                category="Bags",
                brand="UrbanTrail",
                price=1899,
                cost=980,
            ),
        ]
        self._inventory = [
            InventoryItem(
                sku="SKU-1001",
                warehouse="BLR-01",
                available_stock=34,
                reserved_stock=8,
                reorder_point=40,
                supplier_lead_time_days=7,
                safety_stock=20,
                status=StockStatus.low,
            ),
            InventoryItem(
                sku="SKU-1002",
                warehouse="BLR-01",
                available_stock=12,
                reserved_stock=6,
                reorder_point=25,
                supplier_lead_time_days=10,
                safety_stock=15,
                status=StockStatus.critical,
            ),
            InventoryItem(
                sku="SKU-1003",
                warehouse="DEL-02",
                available_stock=118,
                reserved_stock=11,
                reorder_point=35,
                supplier_lead_time_days=5,
                safety_stock=18,
                status=StockStatus.healthy,
            ),
        ]
        self._orders = [
            Order(
                order_id="ORD-9001",
                customer_id="CUS-501",
                items=[OrderItem(sku="SKU-1001", quantity=2, unit_price=1499)],
                total_amount=2998,
                created_at=self._dt("2026-05-18T10:15:00+00:00"),
            ),
            Order(
                order_id="ORD-9002",
                customer_id="CUS-502",
                items=[OrderItem(sku="SKU-1002", quantity=1, unit_price=2299)],
                total_amount=2299,
                created_at=self._dt("2026-05-18T12:20:00+00:00"),
            ),
        ]
        self._returns = [
            ProductReturn(
                return_id="RET-3001",
                order_id="ORD-9001",
                sku="SKU-1001",
                reason=ReturnReason.size_mismatch,
                notes="Customer says shoe runs one size small.",
                created_at=self._dt("2026-05-18T15:30:00+00:00"),
            ),
            ProductReturn(
                return_id="RET-3002",
                order_id="ORD-9002",
                sku="SKU-1002",
                reason=ReturnReason.quality_issue,
                notes="Left earbud battery drains quickly.",
                created_at=self._dt("2026-05-18T18:10:00+00:00"),
            ),
        ]
        self._reviews = [
            Review(
                review_id="REV-7001",
                sku="SKU-1001",
                rating=3,
                title="Comfortable but sizing is off",
                body="Good cushioning, but I had to exchange for a bigger size.",
                created_at=self._dt("2026-05-17T09:45:00+00:00"),
            ),
            Review(
                review_id="REV-7002",
                sku="SKU-1002",
                rating=2,
                title="Battery issue",
                body="Sound is fine, but the battery does not last as advertised.",
                created_at=self._dt("2026-05-18T08:25:00+00:00"),
            ),
        ]
        self._competitors = [
            CompetitorPrice(
                sku="SKU-1001",
                competitor="RunKart",
                price=1399,
                product_url="https://example.com/runkart/aerofit-running-shoes",
                observed_at=self._dt("2026-05-18T06:00:00+00:00"),
                confidence=0.91,
            ),
            CompetitorPrice(
                sku="SKU-1002",
                competitor="GadgetMart",
                price=2199,
                product_url="https://example.com/gadgetmart/voltx-earbuds",
                observed_at=self._dt("2026-05-18T06:10:00+00:00"),
                confidence=0.84,
            ),
        ]

    def list_products(self) -> List[Product]:
        return self._products

    def list_inventory(self) -> List[InventoryItem]:
        return self._inventory

    def list_orders(self) -> List[Order]:
        return self._orders

    def list_returns(self) -> List[ProductReturn]:
        return self._returns

    def list_reviews(self) -> List[Review]:
        return self._reviews

    def list_competitors(self) -> List[CompetitorPrice]:
        return self._competitors

    def upsert_inventory_item(self, item: InventoryItem) -> InventoryItem:
        self._inventory = [
            existing
            for existing in self._inventory
            if not (existing.sku == item.sku and existing.warehouse == item.warehouse)
        ]
        self._inventory.append(item)
        return item

    def add_review(self, review: Review) -> Review:
        self._reviews = [existing for existing in self._reviews if existing.review_id != review.review_id]
        self._reviews.append(review)
        return review

    def add_return(self, product_return: ProductReturn) -> ProductReturn:
        self._returns = [existing for existing in self._returns if existing.return_id != product_return.return_id]
        self._returns.append(product_return)
        return product_return

    def add_competitor_price(self, competitor_price: CompetitorPrice) -> CompetitorPrice:
        self._competitors.append(competitor_price)
        return competitor_price

    def save_agent_run(self, run_record: AgentRunRecord, output_type: str, payload: object) -> None:
        return None

    def create_approval_request(self, approval: ApprovalRequest) -> None:
        return None

    def list_approval_requests(self) -> List[ApprovalRequest]:
        return []

    def update_approval_status(
        self,
        approval_id: str,
        status: ApprovalStatus,
        decided_by: str,
        decided_at: datetime,
    ) -> ApprovalRequest | None:
        return None

    def create_audit_log(self, entry: AuditLogEntry) -> AuditLogEntry:
        return entry

    def list_audit_logs(self, run_id: str | None = None) -> List[AuditLogEntry]:
        return []

    @staticmethod
    def _dt(value: str) -> datetime:
        return datetime.fromisoformat(value).astimezone(timezone.utc)
