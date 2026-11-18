import logging
from datetime import datetime, timezone
from typing import List, Dict, Any
from fastapi import APIRouter, HTTPException, Path, status
from starlette.concurrency import run_in_threadpool
from app.schemas.models import (
    IncidentCreateRequest,
    IncidentResponse,
    HumanReviewRequest,
    AgentTraceItem,
    HealthCheckResponse
)
from app.orchestrator.workflow import incident_store, run_incident_orchestrator
from app.tools.resource_search import load_resources, ResourceDatasetError
from app.config import ACTIVE_PROVIDER

logger = logging.getLogger("resqai.api.routes")
router = APIRouter(prefix="/api", tags=["Incidents & System"])

@router.post(
    "/incidents",
    response_model=IncidentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Submit emergency report and execute 5-agent pipeline"
)
async def create_incident(payload: IncidentCreateRequest):
    """
    Accept an emergency report, sequentially run the 5-agent ResQAI pipeline,
    and return the structured incident record, provisional priority, grounded
    resources, action plan, and verification audit.
    """
    report_text = payload.report.strip()
    if not report_text:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Emergency report cannot be empty."
        )

    try:
        incident_response = await run_in_threadpool(run_incident_orchestrator, report_text)
        return incident_response
    except Exception as e:
        logger.error(f"Error processing incident: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal error processing incident pipeline."
        )

@router.get(
    "/incidents",
    response_model=List[IncidentResponse],
    summary="List all incidents processed during the current session"
)
async def list_incidents():
    """Returns all incidents processed during the active running session."""
    return incident_store.list_all()

@router.get(
    "/incidents/{incident_id}",
    response_model=IncidentResponse,
    summary="Retrieve details for a specific incident"
)
async def get_incident(incident_id: str = Path(..., description="Unique incident identifier, e.g. INC-001")):
    """Returns full details and structured record for the specified incident ID."""
    incident = incident_store.get(incident_id)
    if not incident:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Incident with ID '{incident_id}' was not found in the current session."
        )
    return incident

@router.get(
    "/incidents/{incident_id}/trace",
    response_model=Dict[str, Any],
    summary="Retrieve agent execution trace and performance metrics"
)
async def get_incident_trace(incident_id: str = Path(..., description="Unique incident identifier")):
    """Returns execution statuses, durations, and summaries for all 5 agents."""
    incident = incident_store.get(incident_id)
    if not incident:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Incident with ID '{incident_id}' was not found."
        )
    return {
        "incident_id": incident.incident_id,
        "agents": incident.agents,
        "trace": incident.trace or []
    }

@router.post(
    "/incidents/{incident_id}/review",
    response_model=Dict[str, Any],
    summary="Record human operator review decision"
)
async def review_incident(
    payload: HumanReviewRequest,
    incident_id: str = Path(..., description="Unique incident identifier")
):
    """
    Accepts approve/reject and reviewer notes from human operators.
    Approval records decision support confirmation and does NOT authorize live emergency dispatch.
    """
    incident = incident_store.record_review(incident_id, payload)
    if incident is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Incident with ID '{incident_id}' was not found."
        )

    return {
        "incident_id": incident.incident_id,
        "status": "reviewed",
        "human_review": incident.human_review.model_dump(),
        "disclaimer": (
            "Human review decision recorded successfully. "
            "This approval is an advisory decision-support record and does NOT constitute official emergency dispatch authorization."
        )
    }

@router.get(
    "/health",
    response_model=HealthCheckResponse,
    summary="Backend health and system readiness status"
)
async def health_check():
    """Returns backend health status, active provider, and loaded resources count."""
    try:
        resources = await run_in_threadpool(load_resources)
    except ResourceDatasetError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Backend degraded: synthetic resource dataset unavailable or invalid."
        ) from None
    return HealthCheckResponse(
        status="healthy",
        timestamp=datetime.now(timezone.utc).isoformat(),
        active_provider=ACTIVE_PROVIDER,
        available_resources_count=len(resources),
        system_version="1.0.0",
        disclaimer="ResQAI Decision Support System (Non-dispatch prototype)"
    )
