from app.core.repository import TenantRepository
from app.domains.inventory.models import ProductInventory, InventoryTransaction


class InventoryRepository(TenantRepository):
    def __init__(self, session):
        super().__init__(ProductInventory, session)


class InvTxnRepository(TenantRepository):
    def __init__(self, session):
        super().__init__(InventoryTransaction, session)
