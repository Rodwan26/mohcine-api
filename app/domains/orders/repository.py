from app.core.repository import TenantRepository
from app.domains.orders.models import Order, OrderItem


class OrderRepository(TenantRepository):
    def __init__(self, session):
        super().__init__(Order, session)


class OrderItemRepository(TenantRepository):
    def __init__(self, session):
        super().__init__(OrderItem, session)
