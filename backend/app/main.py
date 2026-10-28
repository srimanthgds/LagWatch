import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import os

from app.core.config import settings
from app.core.database import engine, Base, SessionLocal
from app.simulator.seed_data import seed_database
from app.api.v1 import (
    auth, segments, alarms, work_orders, digs, calibration, risk, kpi, financials, opcua, scenarios, admin
)
from app.api.websocket import router as ws_router, telemetry_background_broadcaster

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: ensure tables exist
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        seed_database(db, force=False)
    finally:
        db.close()
    
    # Start telemetry broadcaster background task
    telemetry_task = asyncio.create_task(telemetry_background_broadcaster())
    yield
    # Shutdown
    telemetry_task.cancel()
    try:
        await telemetry_task
    except asyncio.CancelledError:
        pass

app = FastAPI(
    title=settings.PROJECT_NAME,
    description="Corrosion Under Insulation (CUI) Integrity-Monitoring Platform for Refinery Piping and Vessels. Conforms to ISA-101 and API RP 581.",
    version="4.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/api/openapi.json"
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API v1 Routers
api_v1_prefix = settings.API_V1_STR
app.include_router(auth.router, prefix=api_v1_prefix)
app.include_router(segments.router, prefix=api_v1_prefix)
app.include_router(alarms.router, prefix=api_v1_prefix)
app.include_router(work_orders.router, prefix=api_v1_prefix)
app.include_router(digs.router, prefix=api_v1_prefix)
app.include_router(calibration.router, prefix=api_v1_prefix)
app.include_router(risk.router, prefix=api_v1_prefix)
app.include_router(kpi.router, prefix=api_v1_prefix)
app.include_router(financials.router, prefix=api_v1_prefix)
app.include_router(opcua.router, prefix=api_v1_prefix)
app.include_router(scenarios.router, prefix=api_v1_prefix)
app.include_router(admin.router, prefix=api_v1_prefix)

# WebSocket Router
app.include_router(ws_router)

from fastapi import Request
from fastapi.responses import FileResponse

static_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

@app.get("/")
def health_check(request: Request):
    accept = request.headers.get("accept", "")
    user_agent = request.headers.get("user-agent", "")
    # If accessed from browser, serve dashboard UI
    if "text/html" in accept and not ("python-httpx" in user_agent or accept == "*/*"):
        index_file = os.path.join(static_dir, "index.html")
        if os.path.exists(index_file):
            return FileResponse(index_file)
            
    return {
        "system": "InsulGuard 4.0",
        "status": "OPERATIONAL",
        "standard": "ISA-101 High Performance HMI / API RP 581 RBI",
        "docs": "/docs",
        "api_v1": api_v1_prefix,
        "dashboard": "/dashboard"
    }

@app.get("/dashboard")
def view_dashboard():
    index_file = os.path.join(static_dir, "index.html")
    if os.path.exists(index_file):
        return FileResponse(index_file)
    return {"message": "Dashboard under construction"}
