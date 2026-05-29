from app.core.repository import TenantRepository
from app.domains.pricing.models import ProductPricing


class PricingRepository(TenantRepository):
    def __init__(self, session):
        super().__init__(ProductPricing, session)
