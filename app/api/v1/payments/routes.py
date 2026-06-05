from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.api.deps import AuthContext, require_auth
from app.core.deps import get_uow
from app.core.uow import UnitOfWork
from app.domains.payments.service import PaymentService
from app.domains.payments.schemas import PaymentCreate, PaymentResponse

payment_router = APIRouter(prefix="/payments", tags=["Payments"])


@payment_router.post("", status_code=201, response_model=PaymentResponse)
async def create_payment(
    data: PaymentCreate,
    auth: AuthContext = Depends(require_auth),
    uow: UnitOfWork = Depends(get_uow),
):
    svc = PaymentService(uow)
    try:
        result = await svc.create_payment(
            tenant_id=auth.tenant_id,
            order_id=data.order_id,
            amount=data.amount,
            currency=data.currency,
            provider=data.provider,
            provider_reference=data.provider_reference,
            idempotency_key=data.idempotency_key,
        )
    except ValueError as e:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail=str(e))
    if not result:
        raise HTTPException(status_code=400, detail="Payment creation failed")
    return result


@payment_router.get("/{payment_id}", response_model=PaymentResponse)
async def get_payment(
    payment_id: UUID,
    auth: AuthContext = Depends(require_auth),
    uow: UnitOfWork = Depends(get_uow),
):
    svc = PaymentService(uow)
    result = await svc.get_payment(auth.tenant_id, payment_id)
    if not result:
        raise HTTPException(status_code=404, detail="Payment not found")
    return result


@payment_router.post("/{payment_id}/confirm", response_model=PaymentResponse)
async def confirm_payment(
    payment_id: UUID,
    auth: AuthContext = Depends(require_auth),
    uow: UnitOfWork = Depends(get_uow),
):
    svc = PaymentService(uow)
    try:
        result = await svc.confirm_payment(auth.tenant_id, payment_id)
    except ValueError as e:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail=str(e))
    if not result:
        raise HTTPException(status_code=404, detail="Payment not found")
    return result


@payment_router.post("/{payment_id}/fail", response_model=PaymentResponse)
async def fail_payment(
    payment_id: UUID,
    failure_reason: str | None = Query(None),
    auth: AuthContext = Depends(require_auth),
    uow: UnitOfWork = Depends(get_uow),
):
    svc = PaymentService(uow)
    try:
        result = await svc.fail_payment(
            auth.tenant_id, payment_id, failure_reason=failure_reason,
        )
    except ValueError as e:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail=str(e))
    if not result:
        raise HTTPException(status_code=404, detail="Payment not found")
    return result


@payment_router.post("/{payment_id}/refund", response_model=PaymentResponse)
async def refund_payment(
    payment_id: UUID,
    reason: str | None = Query(None),
    auth: AuthContext = Depends(require_auth),
    uow: UnitOfWork = Depends(get_uow),
):
    svc = PaymentService(uow)
    try:
        result = await svc.refund_payment(
            auth.tenant_id, payment_id, reason=reason,
        )
    except ValueError as e:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail=str(e))
    if not result:
        raise HTTPException(status_code=404, detail="Payment not found")
    return result
