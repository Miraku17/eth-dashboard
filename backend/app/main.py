import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.alerts import router as alerts_router
from app.api.derivatives import router as derivatives_router
from app.api.flows import router as flows_router
from app.api.health import router as health_router
from app.api.leaderboard import router as leaderboard_router
from app.api.network import router as network_router
from app.api.price import router as price_router
from app.api.whales import router as whales_router
from app.core.auth import AuthDep

# Read CORS directly from env so importing this module doesn't require the
# full Pydantic Settings object (which enforces Postgres/Redis envs).
_raw_origins = os.environ.get("CORS_ORIGINS", "*")
_origins = [o.strip() for o in _raw_origins.split(",") if o.strip()]

app = FastAPI(title="Etherscope API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins or ["*"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

# Health stays public so uptime pings + the topbar indicator still work.
app.include_router(health_router, prefix="/api")

# Everything else is gated when API_AUTH_TOKEN is set; passes through otherwise.
app.include_router(price_router, prefix="/api", dependencies=[AuthDep])
app.include_router(flows_router, prefix="/api", dependencies=[AuthDep])
app.include_router(whales_router, prefix="/api", dependencies=[AuthDep])
app.include_router(alerts_router, prefix="/api", dependencies=[AuthDep])
app.include_router(network_router, prefix="/api", dependencies=[AuthDep])
app.include_router(derivatives_router, prefix="/api", dependencies=[AuthDep])
app.include_router(leaderboard_router, prefix="/api", dependencies=[AuthDep])
