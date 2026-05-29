from fastapi import FastAPI

from app.api.v1.router import api_v1_router

app = FastAPI(
    title="Mohcine API",
    description="SaaS e-commerce platform API",
    version="0.1.0",
)

app.include_router(api_v1_router, prefix="/api/v1")


@app.get("/health")
async def health():
    return {"status": "ok", "version": "0.1.0"}
