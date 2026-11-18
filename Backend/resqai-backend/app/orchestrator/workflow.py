import time
import logging
from datetime import datetime, timezone
from threading import Lock
from typing import Dict, Any, List, Optional
from app.schemas.models import (
    IncidentResponse,
    AgentTraceItem,
    IncidentRecord,
    TriageRecord,
    ResourceItem,
    PlanAction,
    VerificationData,
    HumanReviewRecord,
    HumanReviewRequest
)
from app.agents.intake import run_intake_agent
from app.agents.triage import run_triage_agent
from app.agents.resource import run_resource_agent
from app.agents.planning import run_planning_agent
from app.agents.verification import run_verification_agent

logger = logging.getLogger("resqai.orchestrator.workflow")

class IncidentStore:
    """In-memory thread-safe storage for processed incidents during the running session."""
    def __init__(self):
        self._incidents: Dict[str, IncidentResponse] = {}
        self._counter: int = 0
        self._lock = Lock()

    def next_incident_id(self) -> str:
        with self._lock:
            self._counter += 1
            return f"INC-{self._counter:03d}"

    def save(self, incident: IncidentResponse) -> None:
        with self._lock:
            self._incidents[incident.incident_id] = incident.model_copy(deep=True)

    def get(self, incident_id: str) -> Optional[IncidentResponse]:
        with self._lock:
            incident = self._incidents.get(incident_id)
            return incident.model_copy(deep=True) if incident is not None else None

    def list_all(self) -> List[IncidentResponse]:
        with self._lock:
            return [incident.model_copy(deep=True) for incident in self._incidents.values()]

    def record_review(self, incident_id: str, review: HumanReviewRequest) -> Optional[IncidentResponse]:
        """Atomically replace the complete review; the last completed write wins."""
        with self._lock:
            incident = self._incidents.get(incident_id)
            if incident is None:
                return None
            incident.human_review = HumanReviewRecord(
                reviewed=True,
                decision=review.decision,
                reviewer_notes=review.reviewer_notes,
                reviewer_id=review.reviewer_id,
                reviewed_at=datetime.now(timezone.utc).isoformat(),
            )
            return incident.model_copy(deep=True)

incident_store = IncidentStore()

def run_incident_orchestrator(report_text: str) -> IncidentResponse:
    """
    Executes the sequential 5-agent ResQAI pipeline:
    Incident Report -> Intake -> Triage -> Resource -> Planning -> Verification -> Structured Response
    """
    incident_id = incident_store.next_incident_id()
    created_at = datetime.now(timezone.utc).isoformat()
    trace: List[AgentTraceItem] = []

    # Agent execution statuses - initially pending
    agent_statuses: Dict[str, str] = {
        "intake": "pending",
        "triage": "pending",
        "resource": "pending",
        "planning": "pending",
        "verification": "pending"
    }

    # ==========================================
    # 1. Agent 1: Intake Agent
    # ==========================================
    t0 = time.perf_counter()
    intake_record: IncidentRecord
    try:
        intake_record, model_used, error_msg = run_intake_agent(report_text)
        duration = round((time.perf_counter() - t0) * 1000, 2)
        if error_msg:
            # Fallback was used due to error or no key
            agent_statuses["intake"] = "completed"
            summary = f"Extracted category '{intake_record.category}' via {model_used}."
        else:
            agent_statuses["intake"] = "completed"
            summary = f"Extracted category '{intake_record.category}' and location '{intake_record.location}'."

        trace.append(AgentTraceItem(
            agent="intake",
            status="completed",
            model=model_used,
            duration_ms=duration,
            summary=summary,
            details=intake_record.model_dump()
        ))
    except Exception:
        logger.exception("Incident pipeline agent failed")
        duration = round((time.perf_counter() - t0) * 1000, 2)
        agent_statuses["intake"] = "failed"
        trace.append(AgentTraceItem(
            agent="intake",
            status="failed",
            model="unknown",
            duration_ms=duration,
            summary="Intake agent failed to parse report.",
            error="Agent execution failed; consult server logs."
        ))
        intake_record = IncidentRecord(
            category="Unknown",
            location="Unknown / Unspecified",
            missing_information=["Intake parsing failed"]
        )

    # ==========================================
    # 2. Agent 2: Triage Agent
    # ==========================================
    t0 = time.perf_counter()
    triage_record: TriageRecord
    try:
        triage_record, model_used, error_msg = run_triage_agent(intake_record)
        duration = round((time.perf_counter() - t0) * 1000, 2)
        agent_statuses["triage"] = "completed"
        trace.append(AgentTraceItem(
            agent="triage",
            status="completed",
            model=model_used,
            duration_ms=duration,
            summary=f"Assigned provisional priority '{triage_record.priority}'.",
            details=triage_record.model_dump()
        ))
    except Exception:
        logger.exception("Incident pipeline agent failed")
        duration = round((time.perf_counter() - t0) * 1000, 2)
        agent_statuses["triage"] = "failed"
        trace.append(AgentTraceItem(
            agent="triage",
            status="failed",
            model="unknown",
            duration_ms=duration,
            summary="Triage assessment failed.",
            error="Agent execution failed; consult server logs."
        ))
        triage_record = TriageRecord(
            priority="Medium",
            reasoning="Fallback triage due to agent execution error.",
            missing_information=["Triage agent failure"]
        )

    # ==========================================
    # 3. Agent 3: Resource Agent
    # ==========================================
    t0 = time.perf_counter()
    matched_resources: List[ResourceItem] = []
    try:
        matched_resources, model_used, error_msg = run_resource_agent(intake_record, triage_record)
        duration = round((time.perf_counter() - t0) * 1000, 2)
        if error_msg:
            agent_statuses["resource"] = "failed"
            trace.append(AgentTraceItem(
                agent="resource",
                status="failed",
                model=model_used,
                duration_ms=duration,
                summary="Resource retrieval failed.",
                error="Resource retrieval failed; consult server logs."
            ))
        else:
            agent_statuses["resource"] = "completed"
            trace.append(AgentTraceItem(
                agent="resource",
                status="completed",
                model=model_used,
                duration_ms=duration,
                summary=f"Retrieved {len(matched_resources)} grounded synthetic resources.",
                details={"resource_count": len(matched_resources), "ids": [r.resource_id for r in matched_resources]}
            ))
    except Exception:
        logger.exception("Incident pipeline agent failed")
        duration = round((time.perf_counter() - t0) * 1000, 2)
        agent_statuses["resource"] = "failed"
        trace.append(AgentTraceItem(
            agent="resource",
            status="failed",
            model="unknown",
            duration_ms=duration,
            summary="Resource search failed unexpectedly.",
            error="Agent execution failed; consult server logs."
        ))

    # ==========================================
    # 4. Agent 4: Planning Agent
    # ==========================================
    t0 = time.perf_counter()
    action_plan: List[PlanAction] = []
    try:
        action_plan, model_used, error_msg = run_planning_agent(intake_record, triage_record, matched_resources)
        duration = round((time.perf_counter() - t0) * 1000, 2)
        agent_statuses["planning"] = "completed"
        trace.append(AgentTraceItem(
            agent="planning",
            status="completed",
            model=model_used,
            duration_ms=duration,
            summary=f"Generated {len(action_plan)} response actions distinguishing safety guidance from responder actions.",
            details={"action_count": len(action_plan)}
        ))
    except Exception:
        logger.exception("Incident pipeline agent failed")
        duration = round((time.perf_counter() - t0) * 1000, 2)
        agent_statuses["planning"] = "failed"
        trace.append(AgentTraceItem(
            agent="planning",
            status="failed",
            model="unknown",
            duration_ms=duration,
            summary="Planning generation failed.",
            error="Agent execution failed; consult server logs."
        ))

    # ==========================================
    # 5. Agent 5: Verification Agent
    # ==========================================
    t0 = time.perf_counter()
    verification_data: VerificationData
    try:
        verification_data, model_used, error_msg = run_verification_agent(
            record=intake_record,
            triage=triage_record,
            resources=matched_resources,
            actions=action_plan
        )
        duration = round((time.perf_counter() - t0) * 1000, 2)
        agent_statuses["verification"] = "completed"
        trace.append(AgentTraceItem(
            agent="verification",
            status="completed",
            model=model_used,
            duration_ms=duration,
            summary=f"Audited response integrity; verified {len(verification_data.verified_resource_ids)} resources, status='{verification_data.status}'.",
            details=verification_data.model_dump()
        ))
    except Exception:
        logger.exception("Incident pipeline agent failed")
        duration = round((time.perf_counter() - t0) * 1000, 2)
        agent_statuses["verification"] = "failed"
        trace.append(AgentTraceItem(
            agent="verification",
            status="failed",
            model="unknown",
            duration_ms=duration,
            summary="Verification auditor failed.",
            error="Agent execution failed; consult server logs."
        ))
        verification_data = VerificationData(
            status="human_review_required",
            human_review_required=True,
            flags=[
                "Verification agent exception occurred",
                "LOCATION_UNVERIFIED: Independent location verification unavailable; manual address verification required",
                "DECISION_SUPPORT_SAFEGUARD: Automated dispatch disabled; human operator verification mandatory",
            ]
        )

    # Compile combined missing information from Intake and Triage
    combined_missing_info = list(dict.fromkeys(intake_record.missing_information + triage_record.missing_information))

    # Construct final incident response adhering to the exact API contract
    response = IncidentResponse(
        incident_id=incident_id,
        category=intake_record.category,
        priority=triage_record.priority,
        location=intake_record.location,
        affected_people=intake_record.affected_people,
        injuries_reported=intake_record.injuries_reported,
        missing_information=combined_missing_info,
        agents=agent_statuses,
        resources=[r.model_dump() for r in matched_resources],
        action_plan=[a.model_dump() for a in action_plan],
        verification=verification_data.model_dump(),
        raw_report=report_text,
        created_at=created_at,
        trace=trace,
        human_review=HumanReviewRecord()
    )

    incident_store.save(response)
    logger.info(f"Successfully processed and stored incident {incident_id}")
    return response
