from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models import (
    CompetitorPriceModel,
    InventoryItemModel,
    OrderItemModel,
    OrderModel,
    ProductModel,
    ProductReturnModel,
    ReviewModel,
)
from app.ecommerce_ops.repository import EcommerceOpsRepository


def seed_demo_data(session: Session) -> None:
    existing = session.scalar(select(ProductModel.sku).limit(1))
    if existing:
        return

    repository = EcommerceOpsRepository()

    for product in repository.list_products():
        session.add(
            ProductModel(
                sku=product.sku,
                name=product.name,
                category=product.category,
                brand=product.brand,
                price=product.price,
                cost=product.cost,
                active=product.active,
            )
        )
    session.flush()

    for item in repository.list_inventory():
        session.add(
            InventoryItemModel(
                sku=item.sku,
                warehouse=item.warehouse,
                available_stock=item.available_stock,
                reserved_stock=item.reserved_stock,
                reorder_point=item.reorder_point,
                supplier_lead_time_days=item.supplier_lead_time_days,
                safety_stock=item.safety_stock,
                status=item.status.value,
            )
        )

    for order in repository.list_orders():
        order_model = OrderModel(
            order_id=order.order_id,
            customer_id=order.customer_id,
            total_amount=order.total_amount,
            created_at=order.created_at,
        )
        order_model.items = [
            OrderItemModel(
                order_id=order.order_id,
                sku=item.sku,
                quantity=item.quantity,
                unit_price=item.unit_price,
            )
            for item in order.items
        ]
        session.add(order_model)

    for product_return in repository.list_returns():
        session.add(
            ProductReturnModel(
                return_id=product_return.return_id,
                order_id=product_return.order_id,
                sku=product_return.sku,
                reason=product_return.reason.value,
                notes=product_return.notes,
                created_at=product_return.created_at,
            )
        )

    for review in repository.list_reviews():
        session.add(
            ReviewModel(
                review_id=review.review_id,
                sku=review.sku,
                rating=review.rating,
                title=review.title,
                body=review.body,
                created_at=review.created_at,
            )
        )

    for competitor_price in repository.list_competitors():
        session.add(
            CompetitorPriceModel(
                sku=competitor_price.sku,
                competitor=competitor_price.competitor,
                price=competitor_price.price,
                product_url=competitor_price.product_url,
                observed_at=competitor_price.observed_at,
                confidence=competitor_price.confidence,
            )
        )

    session.commit()
