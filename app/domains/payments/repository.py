from app.core.repository import TenantRepository
from app.domains.payments.models import Payment


class PaymentRepository(TenantRepository):
    def __init__(self, session):
        super().__init__(Payment, session)
