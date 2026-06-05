from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.api.deps import AuthContext, require_auth
from app.core.deps import get_uow
from app.core.uow import UnitOfWork
from app.domains.catalog.service import CatalogService
from app.domains.catalog.repository import ProductSpec
from app.domains.catalog.schemas import ProductCreate, ProductUpdate

product_router = APIRouter(prefix="/products", tags=["Products"])


@product_router.get("")
async def list_products(
    cursor: str | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
    search: str | None = Query(None),
    category_id: str | None = Query(None),
    is_active: bool | None = Query(None),
    price_min: float | None = Query(None),
    price_max: float | None = Query(None),
    sort_by: str = Query("created_at"),
    sort_dir: str = Query("desc"),
    auth: AuthContext = Depends(require_auth),
    uow: UnitOfWork = Depends(get_uow),
):
    spec = ProductSpec(
        tenant_id=auth.tenant_id,
        search=search,
        category_id=category_id,
        is_active=is_active,
        price_min=price_min,
        price_max=price_max,
        sort_by=sort_by,
        sort_dir=sort_dir,
    )
    svc = CatalogService(uow)
    return await svc.list_products(auth.tenant_id, spec, cursor, limit)


@product_router.get("/{product_id}")
async def get_product(
    product_id: UUID,
    auth: AuthContext = Depends(require_auth),
    uow: UnitOfWork = Depends(get_uow),
):
    svc = CatalogService(uow)
    result = await svc.get_product(auth.tenant_id, product_id)
    if not result:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Product not found")
    return result


@product_router.post("", status_code=201)
async def create_product(
    data: ProductCreate,
    auth: AuthContext = Depends(require_auth),
    uow: UnitOfWork = Depends(get_uow),
):
    svc = CatalogService(uow)
    return await svc.create_product(auth.tenant_id, data)


@product_router.patch("/{product_id}")
async def update_product(
    product_id: UUID,
    data: ProductUpdate,
    auth: AuthContext = Depends(require_auth),
    uow: UnitOfWork = Depends(get_uow),
):
    svc = CatalogService(uow)
    result = await svc.update_product(auth.tenant_id, product_id, data)
    if not result:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Product not found")
    return result


@product_router.delete("/{product_id}", status_code=204)
async def delete_product(
    product_id: UUID,
    auth: AuthContext = Depends(require_auth),
    uow: UnitOfWork = Depends(get_uow),
):
    svc = CatalogService(uow)
    deleted = await svc.delete_product(auth.tenant_id, product_id)
    if not deleted:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Product not found")
