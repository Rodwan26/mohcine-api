from pydantic import BaseModel


class BootstrapRequest(BaseModel):
    email: str = "admin@mohcine.com"
    password: str
    name: str = "Admin"
    tenant_slug: str = "default"
    tenant_name: str = "Default Store"


class BootstrapResponse(BaseModel):
    bootstrapped: bool
    tenant: dict
    admin: dict


class SystemStatusResponse(BaseModel):
    bootstrapped: bool
    tenant_count: int
