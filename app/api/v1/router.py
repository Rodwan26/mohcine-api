from fastapi import APIRouter, Depends

from app.api.v1.auth.routes import auth_router
from app.api.v1.categories.routes import category_router
from app.api.v1.orders.routes import order_router
from app.api.v1.payments.routes import payment_router
from app.api.v1.products.routes import product_router
from app.api.v1.system.routes import system_router
from app.core.deps import require_tenant

api_v1_router = APIRouter()

# Tenant-required routers
tenant_routers = [
    (order_router, "/orders"),
    (payment_router, "/payments"),
    (product_router, "/products"),
    (category_router, "/categories"),
]
for router, prefix in tenant_routers:
    api_v1_router.include_router(router, prefix=prefix, dependencies=[Depends(require_tenant)])

# Public routers (no tenant enforcement)
api_v1_router.include_router(auth_router, prefix="/auth")
api_v1_router.include_router(system_router, prefix="/system")


@api_v1_router.get("/ping")
async def ping():
    return {"message": "pong"}
