import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.alerts import router as alerts_router
from app.api.auth import router as auth_router
from app.api.clusters import router as clusters_router
from app.api.derivatives import router as derivatives_router
from app.api.flows import router as flows_router
from app.api.health import router as health_router
from app.api.leaderboard import router as leaderboard_router
from app.api.network import router as network_router
from app.api.price import router as price_router
from app.api.staking import router as staking_router
from app.api.wallets import router as wallets_router
from app.api.whales import router as whales_router
from app.core.auth import AuthDep

# Cookie auth requires explicit origins; "*" is incompatible with credentials.
_raw_origins = os.environ.get(
    "CORS_ORIGINS", "http://localhost:5173,http://localhost:3000"
)
_origins = [
    o.strip()
    for o in _raw_origins.split(",")
    if o.strip() and o.strip() != "*"
]

app = FastAPI(title="Etherscope API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type"],
)

# Public routes.
app.include_router(health_router, prefix="/api")
app.include_router(auth_router, prefix="/api")

# Session-gated routes.
app.include_router(price_router, prefix="/api", dependencies=[AuthDep])
app.include_router(flows_router, prefix="/api", dependencies=[AuthDep])
app.include_router(whales_router, prefix="/api", dependencies=[AuthDep])
app.include_router(alerts_router, prefix="/api", dependencies=[AuthDep])
app.include_router(network_router, prefix="/api", dependencies=[AuthDep])
app.include_router(derivatives_router, prefix="/api", dependencies=[AuthDep])
app.include_router(leaderboard_router, prefix="/api", dependencies=[AuthDep])
app.include_router(clusters_router, prefix="/api", dependencies=[AuthDep])
app.include_router(staking_router, prefix="/api", dependencies=[AuthDep])
app.include_router(wallets_router, prefix="/api", dependencies=[AuthDep])
