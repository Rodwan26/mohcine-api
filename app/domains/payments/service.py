from decimal import Decimal
from uuid import UUID

from app.core.outbox import OutboxStore
from app.core.uow import UnitOfWork
from app.domains.payments.models import Payment, PaymentStatus
from app.domains.payments.repository import PaymentRepository
from app.domains.payments.events import PaymentCreated, PaymentSucceeded, PaymentFailed, PaymentRefunded


class PaymentStateMachine:
    TRANSITIONS: dict[PaymentStatus, set[PaymentStatus]] = {
        PaymentStatus.PENDING: {PaymentStatus.AUTHORIZED, PaymentStatus.PAID, PaymentStatus.FAILED, PaymentStatus.CANCELLED},
        PaymentStatus.AUTHORIZED: {PaymentStatus.PAID, PaymentStatus.FAILED, PaymentStatus.CANCELLED},
        PaymentStatus.PAID: {PaymentStatus.REFUNDED},
        PaymentStatus.FAILED: set(),
        PaymentStatus.REFUNDED: set(),
        PaymentStatus.CANCELLED: set(),
    }

    @staticmethod
    def can_transition(from_status: PaymentStatus, to_status: PaymentStatus) -> bool:
        return to_status in PaymentStateMachine.TRANSITIONS.get(from_status, set())

    @staticmethod
    def transition(payment: Payment, to_status: PaymentStatus) -> None:
        from_status = payment.status
        if not PaymentStateMachine.can_transition(from_status, to_status):
            raise ValueError(
                f"Cannot transition from {from_status.value} to {to_status.value}"
            )
        payment.status = to_status


class PaymentService:
    def __init__(self, uow: UnitOfWork):
        self.uow = uow
        self.outbox = OutboxStore(uow.session)
        self.repo = PaymentRepository(uow.session)

    async def create_payment(
        self,
        tenant_id: UUID,
        order_id: UUID,
        amount: Decimal,
        currency: str = "USD",
        provider: str | None = None,
        provider_reference: str | None = None,
        idempotency_key: str | None = None,
    ) -> dict | None:
        if idempotency_key:
            existing = await self.repo.find_one(
                tenant_id=tenant_id, idempotency_key=idempotency_key
            )
            if existing:
                return self._payment_to_response(existing)

        active_statuses = [PaymentStatus.PENDING, PaymentStatus.AUTHORIZED]
        active = await self.repo.find_many(
            self.repo.query().where(
                Payment.order_id == order_id,
                Payment.status.in_(active_statuses),
            )
        )
        if active:
            raise ValueError("Order already has an active payment")

        payment = await self.repo.create(
            tenant_id=tenant_id,
            order_id=order_id,
            amount=amount,
            currency=currency,
            status=PaymentStatus.PENDING,
            provider=provider,
            provider_reference=provider_reference,
            idempotency_key=idempotency_key,
        )

        await self.outbox.append(PaymentCreated(
            payment_id=payment.id,
            order_id=order_id,
            tenant_id=tenant_id,
            amount=amount,
            currency=currency,
        ))

        await self.uow.commit()

        return self._payment_to_response(payment)

    async def confirm_payment(
        self,
        tenant_id: UUID,
        payment_id: UUID,
        provider_reference: str | None = None,
    ) -> dict | None:
        payment = await self.repo.find_one(tenant_id=tenant_id, id=payment_id)
        if not payment:
            return None
        PaymentStateMachine.transition(payment, PaymentStatus.PAID)
        payment.provider_reference = provider_reference or payment.provider_reference
        await self.outbox.append(PaymentSucceeded(
            payment_id=payment_id,
            order_id=payment.order_id,
            tenant_id=tenant_id,
            provider_reference=provider_reference,
        ))
        await self.uow.commit()
        return await self.get_payment(tenant_id, payment_id)

    async def fail_payment(
        self,
        tenant_id: UUID,
        payment_id: UUID,
        failure_reason: str | None = None,
    ) -> dict | None:
        payment = await self.repo.find_one(tenant_id=tenant_id, id=payment_id)
        if not payment:
            return None
        PaymentStateMachine.transition(payment, PaymentStatus.FAILED)
        payment.failure_reason = failure_reason
        await self.outbox.append(PaymentFailed(
            payment_id=payment_id,
            order_id=payment.order_id,
            tenant_id=tenant_id,
            reason=failure_reason,
        ))
        await self.uow.commit()
        return await self.get_payment(tenant_id, payment_id)

    async def refund_payment(
        self,
        tenant_id: UUID,
        payment_id: UUID,
        reason: str | None = None,
    ) -> dict | None:
        payment = await self.repo.find_one(tenant_id=tenant_id, id=payment_id)
        if not payment:
            return None
        PaymentStateMachine.transition(payment, PaymentStatus.REFUNDED)
        payment.failure_reason = reason
        await self.outbox.append(PaymentRefunded(
            payment_id=payment_id,
            order_id=payment.order_id,
            tenant_id=tenant_id,
            reason=reason,
        ))
        await self.uow.commit()
        return await self.get_payment(tenant_id, payment_id)

    async def get_payment(self, tenant_id: UUID, payment_id: UUID) -> dict | None:
        payment = await self.repo.find_one(tenant_id=tenant_id, id=payment_id)
        if not payment:
            return None
        return self._payment_to_response(payment)

    def _payment_to_response(self, payment: Payment) -> dict:
        return {
            "id": str(payment.id),
            "order_id": str(payment.order_id),
            "amount": str(payment.amount),
            "currency": payment.currency,
            "status": payment.status.value if isinstance(payment.status, PaymentStatus) else payment.status,
            "provider": payment.provider,
            "provider_reference": payment.provider_reference,
            "idempotency_key": payment.idempotency_key,
            "version_id": getattr(payment, "version_id", 1),
            "created_at": payment.created_at.isoformat(),
            "updated_at": payment.updated_at.isoformat(),
        }
