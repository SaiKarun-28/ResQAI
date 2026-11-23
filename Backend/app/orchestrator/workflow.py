import time
import json
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from threading import Lock

from app.database import (
    get_connection,
    _row_to_incident,
    _row_to_dispatch_request,
    create_incident,
    update_incident_location,
    update_incident_transcript,
    update_incident_hazard_assessment,
    update_incident_rescue_plan,
    update_incident_approval,
    invalidate_incident_approval,
    record_audit_event,
    get_audit_events,
    list_incidents,
    get_incident,
    create_dispatch_request,
    get_dispatch_requests,
    update_dispatch_request_status,
)
from app.schemas.models import (
    IncidentResponse,
    AgentTraceItem,
    IncidentRecord,
    TriageRecord,
    ResourceItem,
    PlanAction,
    VerificationData,
    HumanReviewRecord,
    HumanReviewRequest,
    DispatchRequest,
    RescuePlan,
)
from app.agents.intake import run_intake_agent
from app.agents.triage import run_triage_agent
from app.agents.geospatial import run_geospatial_agent
from app.agents.resource import run_resource_agent
from app.agents.planning import run_planning_agent
from app.agents.verification import run_verification_agent
from app.agents.coordination import run_coordination_agent
from app.config import ACTIVE_PROVIDER

logger = logging.getLogger("resqai.orchestrator.workflow")


class IncidentStore:
    """SQLite-based persistent storage for processed incidents."""

    def next_incident_id(self) -> str:
        """Generate next incident ID, never colliding with existing rows.

        The sequence counter can drift behind the incidents table (e.g. after a
        partial wipe or seeded rows), so the counter is derived from max existing INC
        and the incident_sequence table. The sequence table is cleared and reset to
        a single row to avoid UNIQUE constraint violations on multi-row sequence tables.
        """
        conn = get_connection()
        with conn:
            max_existing = 0
            for (incident_id,) in conn.execute("SELECT incident_id FROM incidents").fetchall():
                try:
                    max_existing = max(max_existing, int(incident_id.split("-")[1]))
                except (ValueError, IndexError):
                    continue
            counter = conn.execute("SELECT MAX(id) FROM incident_sequence").fetchone()[0] or 0
            new_val = max(counter, max_existing) + 1
            conn.execute("DELETE FROM incident_sequence")
            conn.execute("INSERT INTO incident_sequence (id) VALUES (?)", (new_val,))
        return f"INC-{new_val:03d}"

    def save(self, incident: IncidentResponse) -> None:
        """Persist an incident to SQLite."""
        data = incident.model_dump()

        # Serialize JSON fields
        missing_info = json.dumps(data.get("missing_information", []))
        agents_status = json.dumps(data.get("agents", {}))
        resources = json.dumps(data.get("resources", []))
        action_plan = json.dumps(data.get("action_plan", []))
        verification = json.dumps(data.get("verification", {}))
        hazard_assessment = json.dumps(data.get("hazard_assessment", {})) if data.get("hazard_assessment") else None
        rescue_plan = json.dumps(data.get("rescue_plan", {})) if data.get("rescue_plan") else None
        trace = json.dumps(data.get("trace", []))
        human_review = json.dumps(data.get("human_review", {}))

        create_incident(
            incident_id=data["incident_id"],
            category=data["category"],
            priority=data["priority"],
            location=data["location"],
            location_lat=data.get("location_lat"),
            location_lon=data.get("location_lon"),
            location_accuracy=data.get("location_accuracy"),
            location_source=data.get("location_source"),
            location_timestamp=data.get("location_timestamp"),
            affected_people=data["affected_people"],
            injuries_reported=data["injuries_reported"],
            missing_information=json.loads(missing_info),
            raw_report=data["raw_report"],
            agents_status=json.loads(agents_status),
            resources=json.loads(resources),
            action_plan=json.loads(action_plan),
            verification=json.loads(verification),
            hazard_assessment=json.loads(hazard_assessment) if hazard_assessment else None,
            rescue_plan=json.loads(rescue_plan) if rescue_plan else None,
            trace=json.loads(trace),
        )

        # Record audit event
        record_audit_event(
            incident_id=data["incident_id"],
            actor="system",
            action="incident_created",
            details={"category": data["category"], "priority": data["priority"]}
        )

    def get(self, incident_id: str) -> Optional[IncidentResponse]:
        """Retrieve an incident by ID."""
        data = get_incident(incident_id)
        if data is None:
            return None
        # Ensure agents field is present
        if not data.get("agents") and data.get("agents_status"):
            data["agents"] = data.pop("agents_status")
        # Attach persisted dispatch requests to the API contract
        data["dispatch_requests"] = get_dispatch_requests(incident_id)
        return IncidentResponse(**data)

    def list_all(self) -> List[IncidentResponse]:
        """List all incidents."""
        # list_incidents() returns dicts; wrap each in IncidentResponse before
        # attribute access (matches get()).
        incidents = [IncidentResponse(**i) for i in list_incidents()]
        for incident in incidents:
            incident.dispatch_requests = get_dispatch_requests(incident.incident_id)
        return incidents

    def record_review(self, incident_id: str, review: HumanReviewRequest) -> Optional[IncidentResponse]:
        """Record a human review decision."""
        incident = get_incident(incident_id)
        if not incident:
            return None

        # Get current plan version
        plan_version = 1
        if incident.get("rescue_plan"):
            plan_version = incident["rescue_plan"].get("version", 1)

        # Build review record
        review_data = {
            "reviewed": True,
            "decision": review.decision,
            "reviewer_notes": review.reviewer_notes,
            "reviewer_id": review.reviewer_id,
            "reviewed_at": datetime.now(timezone.utc).isoformat(),
            "plan_version": plan_version,
            "dispatch_authorization_disclaimer": (
                "Human review recorded. This approval is an advisory decision-support record "
                "and does NOT constitute official emergency dispatch authorization."
            ),
        }

        # Update in database
        update_incident_approval(incident_id, plan_version, review_data)

        # Human-in-the-loop gate: simulated dispatch requests are only
        # confirmed (still simulated, never live) once a human approves.
        if review.decision == "approve":
            for req in get_dispatch_requests(incident_id):
                update_dispatch_request_status(req["id"], "approved_simulated")

        # Record audit event
        record_audit_event(
            incident_id=incident_id,
            actor=review.reviewer_id,
            action=f"review_{review.decision}",
            details={"plan_version": plan_version, "notes": review.reviewer_notes}
        )

        return self.get(incident_id)

    def invalidate_approval(self, incident_id: str) -> bool:
        """Invalidate existing approval when plan changes materially."""
        success = invalidate_incident_approval(incident_id)
        if success:
            record_audit_event(
                incident_id=incident_id,
                actor="system",
                action="approval_invalidated",
                details={"reason": "plan_material_change"}
            )
        return success

    def record_audit_event(self, incident_id: str, actor: str, action: str, details: Dict) -> None:
        """Record an audit event."""
        record_audit_event(incident_id, actor, action, details)

    def get_audit_events(self, incident_id: str) -> List[Dict]:
        """Get audit events for an incident."""
        return get_audit_events(incident_id)

    def list_dispatch_requests(self, incident_id: str) -> List[DispatchRequest]:
        """List dispatch requests for an incident."""
        rows = []
        conn = get_connection()
        cursor = conn.execute(
            "SELECT * FROM dispatch_requests WHERE incident_id = ? ORDER BY created_at",
            (incident_id,)
        )
        for row in cursor.fetchall():
            rows.append(_row_to_dispatch_request(row))
        return rows

    def update_dispatch_request_status(self, request_id: int, status: str) -> bool:
        """Update dispatch request status."""
        now = datetime.now(timezone.utc).isoformat()
        conn = get_connection()
        cursor = conn.execute(
            "UPDATE dispatch_requests SET status = ?, updated_at = ? WHERE id = ?",
            (status, now, request_id)
        )
        conn.commit()
        return cursor.rowcount > 0


incident_store = IncidentStore()


def run_incident_orchestrator(report_text: str) -> IncidentResponse:
    """
    Executes the sequential 7-agent ResQAI pipeline with enhanced capabilities.
    """
    incident_id = incident_store.next_incident_id()
    created_at = datetime.now(timezone.utc).isoformat()
    trace: List[AgentTraceItem] = []

    # Agent statuses - will be populated as agents complete
    agent_statuses: Dict[str, str] = {
        "intake": "pending",
        "triage": "pending",
        "geospatial": "pending",
        "resource": "pending",
        "planning": "pending",
        "verification": "pending",
        "coordination": "pending"
    }

    # ==========================================
    # 1. Agent 1: Intake Agent
    # ==========================================
    t0 = time.perf_counter()
    intake_record: IncidentRecord
    try:
        intake_record, model_used, error_msg = run_intake_agent(report_text)
        duration = round((time.perf_counter() - t0) * 1000, 2)
        agent_statuses["intake"] = "completed"
        summary = f"Extracted category '{intake_record.category}' via {model_used}."
        trace.append(AgentTraceItem(
            agent="intake",
            status="completed",
            model=model_used,
            duration_ms=duration,
            summary=summary,
            details=intake_record.model_dump()
        ))
    except Exception as e:
        logger.exception("Intake agent failed")
        duration = round((time.perf_counter() - t0) * 1000, 2)
        agent_statuses["intake"] = "failed"
        summary = "Intake parsing failed"
        trace.append(AgentTraceItem(
            agent="intake",
            status="failed",
            model="unknown",
            duration_ms=duration,
            summary=summary,
            error="Internal error"
        ))
        intake_record = IncidentRecord(
            category="Unknown",
            location="Unknown / Unspecified",
            affected_people=None,
            injuries_reported=False,
            hazards=[],
            missing_information=["Intake parsing failed"],
            notes="Intake parsing failed"
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
        summary = f"Assigned provisional priority '{triage_record.priority}'."
        trace.append(AgentTraceItem(
            agent="triage",
            status="completed",
            model=model_used,
            duration_ms=duration,
            summary=summary,
            details=triage_record.model_dump()
        ))
    except Exception as e:
        logger.exception("Triage agent failed")
        duration = round((time.perf_counter() - t0) * 1000, 2)
        agent_statuses["triage"] = "failed"
        summary = "Triage assessment failed"
        trace.append(AgentTraceItem(
            agent="triage",
            status="failed",
            model="unknown",
            duration_ms=duration,
            summary=summary,
            error="Internal error"
        ))
        triage_record = TriageRecord(
            priority="Medium",
            reasoning="Fallback triage due to agent execution error.",
            urgency_indicators=[],
            uncertainty_flags=["Triage agent failure"],
            missing_information=["Triage agent failure"],
            disclaimer="Provisional AI assessment only; not an official emergency severity classification."
        )

    # ==========================================
    # 3. Agent 3: Geospatial Agent
    # ==========================================
    t0 = time.perf_counter()
    try:
        hazard_assessment, model_used, error_msg = run_geospatial_agent(intake_record)
        duration = round((time.perf_counter() - t0) * 1000, 2)
        agent_statuses["geospatial"] = "completed"
        summary = f"Geospatial hazard-zone check returned status '{hazard_assessment.status}'."
        trace.append(AgentTraceItem(
            agent="geospatial",
            status="completed",
            model=model_used,
            duration_ms=duration,
            summary=summary,
            details=hazard_assessment.model_dump()
        ))
    except Exception as e:
        logger.exception("Geospatial agent failed")
        duration = round((time.perf_counter() - t0) * 1000, 2)
        agent_statuses["geospatial"] = "failed"
        summary = "Geospatial assessment failed."
        trace.append(AgentTraceItem(
            agent="geospatial",
            status="failed",
            model="unknown",
            duration_ms=duration,
            summary=summary,
            error="Internal error"
        ))
        hazard_assessment = None

    # ==========================================
    # 4. Agent 4: Resource Agent
    # ==========================================
    t0 = time.perf_counter()
    matched_resources: List[ResourceItem] = []
    try:
        matched_resources, model_used, error_msg = run_resource_agent(intake_record, triage_record)
        duration = round((time.perf_counter() - t0) * 1000, 2)
        if error_msg:
            agent_statuses["resource"] = "failed"
            summary = "Resource retrieval failed"
            trace.append(AgentTraceItem(
                agent="resource",
                status="failed",
                model=model_used,
                duration_ms=duration,
                summary=summary,
                error=error_msg
            ))
        else:
            agent_statuses["resource"] = "completed"
            summary = f"Retrieved {len(matched_resources)} grounded synthetic resources."
            trace.append(AgentTraceItem(
                agent="resource",
                status="completed",
                model=model_used,
                duration_ms=duration,
                summary=summary,
                details={"resource_count": len(matched_resources), "ids": [r.resource_id for r in matched_resources]}
            ))
    except Exception as e:
        logger.exception("Resource agent failed")
        duration = round((time.perf_counter() - t0) * 1000, 2)
        agent_statuses["resource"] = "failed"
        summary = "Resource search failed unexpectedly."
        trace.append(AgentTraceItem(
            agent="resource",
            status="failed",
            model="unknown",
            duration_ms=duration,
            summary=summary,
            error="Internal error"
        ))

    # ==========================================
    # 5. Agent 5: Planning Agent
    # ==========================================
    t0 = time.perf_counter()
    action_plan: List[PlanAction] = []
    try:
        action_plan, model_used, error_msg = run_planning_agent(intake_record, triage_record, matched_resources)
        duration = round((time.perf_counter() - t0) * 1000, 2)
        agent_statuses["planning"] = "completed"
        summary = f"Generated {len(action_plan)} response actions distinguishing safety guidance from responder actions."
        trace.append(AgentTraceItem(
            agent="planning",
            status="completed",
            model=model_used,
            duration_ms=duration,
            summary=summary,
            details={"action_count": len(action_plan)}
        ))
    except Exception as e:
        logger.exception("Planning agent failed")
        duration = round((time.perf_counter() - t0) * 1000, 2)
        agent_statuses["planning"] = "failed"
        summary = "Planning generation failed."
        trace.append(AgentTraceItem(
            agent="planning",
            status="failed",
            model="unknown",
            duration_ms=duration,
            summary=summary,
            error="Internal error"
        ))

    # ==========================================
    # 6. Agent 6: Verification Agent
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
        summary = f"Audited response integrity; verified {len(verification_data.verified_resource_ids)} resources, status='{verification_data.status}'."
        trace.append(AgentTraceItem(
            agent="verification",
            status="completed",
            model=model_used,
            duration_ms=duration,
            summary=summary,
            details=verification_data.model_dump()
        ))
    except Exception as e:
        logger.exception("Verification agent failed")
        duration = round((time.perf_counter() - t0) * 1000, 2)
        agent_statuses["verification"] = "failed"
        summary = "Verification auditor failed."
        trace.append(AgentTraceItem(
            agent="verification",
            status="failed",
            model="unknown",
            duration_ms=duration,
            summary=summary,
            error="Internal error"
        ))
        verification_data = VerificationData(
            status="human_review_required",
            human_review_required=True,
            flags=[
                "Verification agent exception occurred",
                "LOCATION_UNVERIFIED: Independent location verification unavailable; manual address verification required",
                "DECISION_SUPPORT_SAFEGUARD: Automated dispatch disabled; human operator verification mandatory"
            ]
        )

    # ==========================================
    # 7. Agent 7: Coordination Agent (Simulated Dispatch)
    # ==========================================
    t0 = time.perf_counter()
    coordination_data: Dict = {}
    try:
        coordination_data, model_used, error_msg = run_coordination_agent(
            record=intake_record,
            triage=triage_record,
            resources=matched_resources,
            action_plan=action_plan,
            verification=verification_data
        )
        duration = round((time.perf_counter() - t0) * 1000, 2)
        agent_statuses["coordination"] = "completed"
        summary = f"Simulated dispatch requests created for {len(coordination_data)} resource categories."
        trace.append(AgentTraceItem(
            agent="coordination",
            status="completed",
            model=model_used,
            duration_ms=duration,
            summary=summary,
            details=coordination_data
        ))
    except Exception as e:
        logger.exception("Coordination agent failed")
        duration = round((time.perf_counter() - t0) * 1000, 2)
        agent_statuses["coordination"] = "failed"
        summary = "Coordination agent failed."
        trace.append(AgentTraceItem(
            agent="coordination",
            status="failed",
            model="unknown",
            duration_ms=duration,
            summary=summary,
            error="Internal error"
        ))
        coordination_data = {}

    # ==========================================
    # 8. Compile final incident response
    # ==========================================
    combined_missing_info = list(dict.fromkeys(intake_record.missing_information + triage_record.missing_information))

    # Build the rescue plan (Phase 5) from the verified action plan.
    rescue_plan = RescuePlan(
        id=f"PLN-{incident_id}",
        incident_id=incident_id,
        version=1,
        plan_json={
            "category": intake_record.category,
            "priority": triage_record.priority,
            "actions": [a.model_dump() for a in action_plan],
        },
        assumptions=verification_data.unsupported_claims or ["No formal emergency service confirmation received."],
        evidence_references=verification_data.verified_resource_ids or [],
        verification_result=verification_data.model_dump(),
        created_at=created_at,
    )

    # Persist the rescue plan independently (also stored with the incident below).
    update_incident_rescue_plan(incident_id, rescue_plan.model_dump(), rescue_plan.version)

    # Build the final response (dispatch requests are attached after the
    # incident row is persisted, below).
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
        trace=trace,
        human_review=HumanReviewRecord(),
        rescue_plan=rescue_plan,
        dispatch_requests=[],
    )

    # Persist the incident row FIRST. Dispatch requests carry a foreign key to
    # the incidents table, so the row must exist before any are inserted.
    incident_store.save(response)

    # Persist simulated dispatch requests (Phase 7). Human approval (via /review)
    # later confirms them; they are always simulated, never live dispatch.
    for category, sim in coordination_data.items():
        create_dispatch_request(
            incident_id=incident_id,
            plan_id=rescue_plan.id,
            resource_category=category,
            quantity=1,
            rationale=f"Simulated dispatch for {sim.get('resource_id', category)} (action step {sim.get('step', '?')}). "
                      f"Awaiting human operator approval before confirmation.",
        )
    response.dispatch_requests = get_dispatch_requests(incident_id)

    logger.info(f"Successfully processed and stored incident {incident_id}")
    return response