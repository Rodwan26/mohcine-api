from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.api.deps import AuthContext, require_auth
from app.core.deps import get_uow
from app.core.uow import UnitOfWork
from app.domains.orders.service import OrderService
from app.domains.orders.schemas import OrderCreate, OrderResponse, OrderListResponse

order_router = APIRouter(tags=["Orders"])


@order_router.post("", status_code=201, response_model=OrderResponse)
async def create_order(
    data: OrderCreate,
    auth: AuthContext = Depends(require_auth),
    uow: UnitOfWork = Depends(get_uow),
):
    svc = OrderService(uow)
    result = await svc.create_order(
        tenant_id=auth.tenant_id,
        user_id=auth.user.id,
        items_data=[i.model_dump() for i in data.items],
        currency=data.currency,
        notes=data.notes,
        idempotency_key=data.idempotency_key,
    )
    if not result:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="Order creation failed")
    return result


@order_router.get("", response_model=OrderListResponse)
async def list_orders(
    status: str | None = Query(None),
    cursor: str | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
    auth: AuthContext = Depends(require_auth),
    uow: UnitOfWork = Depends(get_uow),
):
    svc = OrderService(uow)
    return await svc.list_orders(
        tenant_id=auth.tenant_id,
        status=status,
        cursor=cursor,
        limit=limit,
    )


@order_router.get("/{order_id}", response_model=OrderResponse)
async def get_order(
    order_id: UUID,
    auth: AuthContext = Depends(require_auth),
    uow: UnitOfWork = Depends(get_uow),
):
    svc = OrderService(uow)
    result = await svc.get_order(auth.tenant_id, order_id)
    if not result:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Order not found")
    return result


@order_router.post("/{order_id}/cancel", response_model=OrderResponse)
async def cancel_order(
    order_id: UUID,
    auth: AuthContext = Depends(require_auth),
    uow: UnitOfWork = Depends(get_uow),
):
    svc = OrderService(uow)
    try:
        result = await svc.cancel_order(auth.tenant_id, order_id)
    except ValueError as e:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail=str(e))
    if not result:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Order not found")
    return result


@order_router.post("/{order_id}/confirm", response_model=OrderResponse)
async def confirm_order(
    order_id: UUID,
    auth: AuthContext = Depends(require_auth),
    uow: UnitOfWork = Depends(get_uow),
):
    svc = OrderService(uow)
    try:
        result = await svc.confirm_order(auth.tenant_id, order_id)
    except ValueError as e:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail=str(e))
    if not result:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Order not found")
    return result
