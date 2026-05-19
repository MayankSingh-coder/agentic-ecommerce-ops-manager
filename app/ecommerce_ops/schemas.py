from datetime import datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class StockStatus(str, Enum):
    healthy = "healthy"
    low = "low"
    critical = "critical"
    out_of_stock = "out_of_stock"


class ReturnReason(str, Enum):
    damaged = "damaged"
    size_mismatch = "size_mismatch"
    quality_issue = "quality_issue"
    late_delivery = "late_delivery"
    changed_mind = "changed_mind"


class Product(BaseModel):
    sku: str
    name: str
    category: str
    brand: str
    price: float = Field(gt=0)
    cost: float = Field(gt=0)
    active: bool = True


class InventoryItem(BaseModel):
    sku: str
    warehouse: str
    available_stock: int = Field(ge=0)
    reserved_stock: int = Field(ge=0)
    reorder_point: int = Field(ge=0)
    supplier_lead_time_days: int = Field(ge=0)
    safety_stock: int = Field(ge=0)
    status: StockStatus


class OrderItem(BaseModel):
    sku: str
    quantity: int = Field(gt=0)
    unit_price: float = Field(gt=0)


class Order(BaseModel):
    order_id: str
    customer_id: str
    items: List[OrderItem]
    total_amount: float = Field(gt=0)
    created_at: datetime


class ProductReturn(BaseModel):
    return_id: str
    order_id: str
    sku: str
    reason: ReturnReason
    notes: Optional[str] = None
    created_at: datetime


class Review(BaseModel):
    review_id: str
    sku: str
    rating: int = Field(ge=1, le=5)
    title: str
    body: str
    created_at: datetime


class CompetitorPrice(BaseModel):
    sku: str
    competitor: str
    price: float = Field(gt=0)
    product_url: str
    observed_at: datetime
    confidence: float = Field(ge=0, le=1)

