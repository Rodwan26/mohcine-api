from fastapi import APIRouter

from app.api.v1.auth.routes import auth_router
from app.api.v1.orders.routes import order_router
from app.api.v1.payments.routes import payment_router

api_v1_router = APIRouter()

api_v1_router.include_router(auth_router)
api_v1_router.include_router(order_router)
api_v1_router.include_router(payment_router)


@api_v1_router.get("/ping")
async def ping():
    return {"message": "pong"}
