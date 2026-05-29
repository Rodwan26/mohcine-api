from app.core.repository import TenantRepository
from app.models.inventory_transaction import InventoryTransaction


class InventoryTransactionRepository(TenantRepository):
    def __init__(self, session):
        super().__init__(InventoryTransaction, session)
