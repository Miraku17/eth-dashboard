from fastapi import FastAPI

from app.api.flows import router as flows_router
from app.api.health import router as health_router
from app.api.price import router as price_router
from app.api.whales import router as whales_router

app = FastAPI(title="Etherscope API", version="0.1.0")
app.include_router(health_router, prefix="/api")
app.include_router(price_router, prefix="/api")
app.include_router(flows_router, prefix="/api")
app.include_router(whales_router, prefix="/api")
