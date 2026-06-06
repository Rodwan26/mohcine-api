import os

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.system.schemas import BootstrapRequest, BootstrapResponse, SystemStatusResponse
from app.core.database import get_db
from app.services.bootstrap import BootstrapService

system_router = APIRouter(prefix="/system", tags=["system"])


async def verify_setup_key(setup_key: str = Header(alias="X-Setup-Key")) -> None:
    expected = os.getenv("SETUP_KEY")
    if not expected:
        raise HTTPException(
            status_code=403,
            detail={"error": {"code": "SETUP_KEY_NOT_CONFIGURED", "message": "Setup key is not configured on the server"}},
        )
    if setup_key != expected:
        raise HTTPException(
            status_code=403,
            detail={"error": {"code": "INVALID_SETUP_KEY", "message": "Invalid setup key"}},
        )


def get_bootstrap_service(db: AsyncSession = Depends(get_db)) -> BootstrapService:
    return BootstrapService(db=db)


@system_router.get("/status")
async def system_status(
    service: BootstrapService = Depends(get_bootstrap_service),
) -> SystemStatusResponse:
    status = await service.status()
    return status


@system_router.post("/bootstrap")
async def bootstrap(
    body: BootstrapRequest,
    service: BootstrapService = Depends(get_bootstrap_service),
    _=Depends(verify_setup_key),
) -> BootstrapResponse:
    result = await service.bootstrap(
        tenant_slug=body.tenant_slug,
        tenant_name=body.tenant_name,
        admin_email=body.email,
        admin_password=body.password,
        admin_name=body.name,
    )
    return result
