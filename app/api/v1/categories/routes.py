from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.api.deps import AuthContext, require_auth
from app.core.deps import get_uow
from app.core.uow import UnitOfWork
from app.domains.catalog.service import CatalogService
from app.domains.catalog.repository import CategorySpec
from app.domains.catalog.schemas import CategoryCreate, CategoryUpdate

category_router = APIRouter(tags=["Categories"])


@category_router.get("")
async def list_categories(
    search: str | None = Query(None),
    is_active: bool | None = Query(None),
    auth: AuthContext = Depends(require_auth),
    uow: UnitOfWork = Depends(get_uow),
):
    spec = CategorySpec(tenant_id=auth.tenant_id, search=search, is_active=is_active)
    svc = CatalogService(uow)
    return await svc.list_categories(auth.tenant_id, spec)


@category_router.get("/tree")
async def get_category_tree(
    auth: AuthContext = Depends(require_auth),
    uow: UnitOfWork = Depends(get_uow),
):
    svc = CatalogService(uow)
    return await svc.get_category_tree()


@category_router.get("/{category_id}")
async def get_category(
    category_id: UUID,
    auth: AuthContext = Depends(require_auth),
    uow: UnitOfWork = Depends(get_uow),
):
    svc = CatalogService(uow)
    result = await svc.get_category(auth.tenant_id, category_id)
    if not result:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Category not found")
    return result


@category_router.post("", status_code=201)
async def create_category(
    data: CategoryCreate,
    auth: AuthContext = Depends(require_auth),
    uow: UnitOfWork = Depends(get_uow),
):
    svc = CatalogService(uow)
    return await svc.create_category(auth.tenant_id, data)


@category_router.patch("/{category_id}")
async def update_category(
    category_id: UUID,
    data: CategoryUpdate,
    auth: AuthContext = Depends(require_auth),
    uow: UnitOfWork = Depends(get_uow),
):
    svc = CatalogService(uow)
    result = await svc.update_category(auth.tenant_id, category_id, data)
    if not result:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Category not found")
    return result


@category_router.delete("/{category_id}", status_code=204)
async def delete_category(
    category_id: UUID,
    auth: AuthContext = Depends(require_auth),
    uow: UnitOfWork = Depends(get_uow),
):
    svc = CatalogService(uow)
    deleted = await svc.delete_category(auth.tenant_id, category_id)
    if not deleted:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Category not found")
