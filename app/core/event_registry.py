from app.domains.inventory.service import handle_product_created as inventory_handler
from app.domains.orders.service import handle_order_created
from app.domains.pricing.service import handle_product_created as pricing_handler

EVENT_HANDLERS: dict[str, list] = {
    "OrderCreated": [handle_order_created],
    "ProductCreated": [pricing_handler, inventory_handler],
}
