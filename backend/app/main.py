from fastapi import FastAPI

from app.api.health import router as health_router
from app.api.price import router as price_router

app = FastAPI(title="Eth Analytics API", version="0.1.0")
app.include_router(health_router, prefix="/api")
app.include_router(price_router, prefix="/api")
