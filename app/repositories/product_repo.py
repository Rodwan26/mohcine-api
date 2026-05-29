from app.core.repository import TenantRepository
from app.models.product import Product
from app.models.product_pricing import ProductPricing
from app.models.product_inventory import ProductInventory
from app.models.product_variant import ProductVariant


class ProductRepository(TenantRepository):
    def __init__(self, session):
        super().__init__(Product, session)


class ProductPricingRepository(TenantRepository):
    def __init__(self, session):
        super().__init__(ProductPricing, session)


class ProductInventoryRepository(TenantRepository):
    def __init__(self, session):
        super().__init__(ProductInventory, session)


class ProductVariantRepository(TenantRepository):
    def __init__(self, session):
        super().__init__(ProductVariant, session)
