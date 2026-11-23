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
    HealthCheckResponse,
    LocationUpdateRequest,
    TranscriptUpdateRequest
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
    summary="Submit emergency report and execute 7-agent pipeline"
)
async def create_incident(payload: IncidentCreateRequest):
    """
    Accept an emergency report, sequentially run the 7-agent ResQAI pipeline,
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
    """Returns execution statuses, durations, and summaries for all 7 agents."""
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
    "/incidents/{incident_id}/location",
    response_model=Dict[str, Any],
    summary="Update incident with GPS or manual location"
)
async def update_incident_location(
    payload: LocationUpdateRequest,
    incident_id: str = Path(..., description="Unique incident identifier")
):
    """
    Store GPS/manual location with source, accuracy, and timestamp.
    Only one location per incident; subsequent updates replace previous.
    After location is stored, run geospatial hazard-zone assessment.
    """
    # Validate incident exists
    incident = incident_store.get(incident_id)
    if not incident:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Incident with ID '{incident_id}' was not found."
        )

    # Reject overly imprecise coordinates
    if payload.accuracy is not None and payload.accuracy > 5000:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Location accuracy {payload.accuracy}m exceeds maximum allowed 5000m."
        )

    from app.database import update_incident_location as db_update_location
    success = db_update_location(
        incident_id=incident_id,
        lat=payload.latitude,
        lon=payload.longitude,
        accuracy=payload.accuracy,
        source=payload.source,
        timestamp=payload.timestamp,
    )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update location."
        )

    # Run geospatial hazard-zone assessment with new coordinates.
    # IncidentResponse carries `category` (not a `hazards` list), which is used
    # as the hazard-type hint for the point-in-polygon assessment.
    from app.agents.geospatial import run_geospatial_assessment
    hazard_assessment = run_geospatial_assessment(
        location_lat=payload.latitude,
        location_lon=payload.longitude,
        hazard_type_hint=incident.category,
    )

    from app.database import update_incident_hazard_assessment
    update_incident_hazard_assessment(incident_id, hazard_assessment.model_dump())

    # Record audit event for location update
    from app.database import record_audit_event
    record_audit_event(
        incident_id=incident_id,
        actor="user",
        action="location_updated",
        details={
            "latitude": payload.latitude,
            "longitude": payload.longitude,
            "accuracy": payload.accuracy,
            "source": payload.source,
        }
    )

    # Record audit event for geospatial assessment
    record_audit_event(
        incident_id=incident_id,
        actor="system",
        action="geospatial_assessment_completed",
        details={
            "status": hazard_assessment.status,
            "polygon_id": hazard_assessment.polygon_id,
            "hazard_type": hazard_assessment.hazard_type,
            "inside_polygon": hazard_assessment.inside_polygon,
        }
    )

    return {
        "incident_id": incident_id,
        "status": "location_updated",
        "location": {
            "latitude": payload.latitude,
            "longitude": payload.longitude,
            "accuracy": payload.accuracy,
            "source": payload.source,
            "timestamp": payload.timestamp,
        },
        "hazard_assessment": hazard_assessment.model_dump(),
        "disclaimer": "Location recorded for decision support. Independent verification required for official dispatch."
    }

@router.post(
    "/incidents/{incident_id}/transcript",
    response_model=Dict[str, Any],
    summary="Update incident with voice transcript"
)
async def update_incident_transcript(
    payload: TranscriptUpdateRequest,
    incident_id: str = Path(..., description="Unique incident identifier")
):
    """
    Store voice transcript with optional confidence score.
    Transcript replaces previous raw_report; confidence is stored separately.
    """
    # Validate incident exists
    incident = incident_store.get(incident_id)
    if not incident:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Incident with ID '{incident_id}' was not found."
        )

    from app.database import update_incident_transcript as db_update_transcript
    success = db_update_transcript(
        incident_id=incident_id,
        transcript=payload.transcript,
        confidence=payload.confidence,
    )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update transcript."
        )

    # Record audit event
    from app.database import record_audit_event
    record_audit_event(
        incident_id=incident_id,
        actor="user",
        action="transcript_updated",
        details={
            "transcript_length": len(payload.transcript),
            "confidence": payload.confidence,
        }
    )

    return {
        "incident_id": incident_id,
        "status": "transcript_updated",
        "transcript": payload.transcript,
        "confidence": payload.confidence,
        "disclaimer": "Transcript is machine-generated and may contain errors. User review and correction required before submission."
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