import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import CORS_ORIGINS
from app.api.routes import router as api_router
from app.api.weather import router as weather_router
from app.tools.resource_search import load_resources, ResourceDatasetError
from app.database import initialize_database, get_connection

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("resqai.main")


async def startup_event():
    try:
        initialize_database()
        logger.info("Database initialized successfully")
        resources = load_resources()
    except ResourceDatasetError:
        # Keep diagnostics reachable and allow a subsequent load to recover.
        logger.error("ResQAI Backend started in degraded mode: synthetic resource dataset unavailable.", exc_info=True)
    else:
        logger.info("ResQAI Backend started successfully. Loaded %s synthetic resources.", len(resources))


@asynccontextmanager
async def lifespan(application: FastAPI):
    await startup_event()
    yield


app = FastAPI(
    title="ResQAI – Autonomous Emergency Intelligence & Response Coordination",
    description=(
        "Decision-support multi-agent prototype for emergency report intake, "
        "provisional urgency triage, resource matching, response planning, and verification audit. "
        "NOT an official emergency dispatch system."
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(api_router)
app.include_router(weather_router)


@app.get("/", summary="ResQAI API Information")
async def root():
    return {
        "system": "ResQAI – Autonomous Emergency Intelligence & Response Coordination",
        "description": "Multi-agent emergency decision support system",
        "version": "1.0.0",
        "endpoints": {
            "create_incident": "POST /api/incidents",
            "list_incidents": "GET /api/incidents",
            "get_incident": "GET /api/incidents/{incident_id}",
            "get_trace": "GET /api/incidents/{incident_id}/trace",
            "review_incident": "POST /api/incidents/{incident_id}/review",
            "health_check": "GET /api/health",
            "documentation": "/docs"
        },
        "disclaimer": "ResQAI is a decision-support prototype, NOT an authorized emergency dispatch system."
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
