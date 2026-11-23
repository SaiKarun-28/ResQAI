import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.orchestrator.workflow import incident_store

client = TestClient(app)

def test_health_endpoint():
    """Verify backend health status."""
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["available_resources_count"] >= 10
    assert "disclaimer" in data

def test_contract_compliance_flood_with_injuries():
    """
    Test Case 1: Flood emergency with injuries.
    Validates exact API contract shape and field types.
    """
    payload = {"report": "Flood near school. Two people injured."}
    response = client.post("/api/incidents", json=payload)
    assert response.status_code == 201

    data = response.json()

    # Exact required fields per contract
    assert "incident_id" in data
    assert data["incident_id"].startswith("INC-")
    assert data["category"] == "Flood"
    assert data["priority"] == "Critical"
    assert "school" in data["location"].lower()
    assert data["affected_people"] == 2
    assert data["injuries_reported"] is True
    assert isinstance(data["missing_information"], list)
    assert isinstance(data["agents"], dict)

    # Agents execution check
    for agent_name in ["intake", "triage", "resource", "planning", "verification"]:
        assert agent_name in data["agents"]
        assert data["agents"][agent_name] in ["completed", "failed"]

    # Resources check - grounded synthetic records
    assert isinstance(data["resources"], list)
    assert len(data["resources"]) > 0
    for res in data["resources"]:
        assert "resource_id" in res
        assert "name" in res
        assert "resource_type" in res

    # Action plan check
    assert isinstance(data["action_plan"], list)
    assert len(data["action_plan"]) > 0
    has_safety_guidance = any(a["action_type"] == "safety_guidance" for a in data["action_plan"])
    has_professional_action = any(a["action_type"] == "professional_judgment_action" for a in data["action_plan"])
    assert has_safety_guidance, "Plan must contain public safety guidance"
    assert has_professional_action, "Plan must contain professional judgment action"

    # Verification check
    assert "verification" in data
    assert data["verification"]["status"] == "human_review_required"
    assert data["verification"]["human_review_required"] is True
    assert isinstance(data["verification"]["flags"], list)

def test_case_2_fire_emergency():
    """Test Case 2: Fire emergency."""
    payload = {"report": "Heavy fire burning on 2nd floor of warehouse on Maple Street. Smoke filling street."}
    response = client.post("/api/incidents", json=payload)
    assert response.status_code == 201
    data = response.json()

    assert data["category"] == "Fire"
    assert data["priority"] in ["Critical", "High"]
    # Check that fire or rescue resources are present
    resource_types = [r["resource_type"] for r in data["resources"]]
    assert any("Fire" in t or "Hospital" in t or "Shelter" in t for t in resource_types)
    assert data["verification"]["status"] == "human_review_required"

def test_case_3_vague_report_missing_location():
    """Test Case 3: Vague emergency report with missing location."""
    payload = {"report": "Help water is rising quickly everywhere, people stuck!"}
    response = client.post("/api/incidents", json=payload)
    assert response.status_code == 201
    data = response.json()

    assert data["category"] == "Flood"
    # Location should be marked unknown or unverified
    missing_text = " ".join(data["missing_information"]).lower()
    assert "location" in missing_text or "address" in missing_text or "coordinates" in missing_text or data["location"] == "Unknown / Unspecified"
    # Verification should flag unverified location
    verification_flags = " ".join(data["verification"]["flags"])
    assert "LOCATION_UNVERIFIED" in verification_flags or "location" in verification_flags.lower()

def test_case_4_contradictory_or_incomplete_info():
    """Test Case 4: Incomplete / contradictory report."""
    payload = {"report": "Strange explosion heard somewhere, no idea what happened or if anyone is around."}
    response = client.post("/api/incidents", json=payload)
    assert response.status_code == 201
    data = response.json()

    assert len(data["missing_information"]) > 0
    assert data["verification"]["status"] == "human_review_required"

def test_case_5_llm_failure_and_fallback(monkeypatch):
    """
    Test Case 5: LLM API failure resilience.
    Verifies that the orchestrator uses the deterministic fallback smoothly when LLM call fails.
    """
    from app.orchestrator.workflow import run_incident_orchestrator
    from app.tools import llm_client
    calls = []

    def failing_provider(*args, **kwargs):
        calls.append(True)
        raise RuntimeError("Simulated offline provider outage")

    monkeypatch.setattr(llm_client, "call_gemini_api", failing_provider)
    monkeypatch.setattr(llm_client, "call_groq_api", failing_provider)
    # Run directly with a severe flood report
    incident = run_incident_orchestrator("Flash flood swept cars on Highway 10. 4 people trapped.")
    assert incident.incident_id.startswith("INC-")
    assert incident.category == "Flood"
    assert incident.priority in ["Critical", "High"]
    assert incident.affected_people == 4
    assert incident.agents["intake"] == "completed"
    assert incident.agents["triage"] == "completed"
    assert incident.agents["resource"] == "completed"
    assert incident.agents["planning"] == "completed"
    assert incident.agents["verification"] == "completed"
    assert calls, "The provider failure stubs must actually run"
    for trace in incident.trace:
        if trace.agent in {"intake", "triage", "planning"}:
            assert trace.model.startswith("deterministic-")

def test_incident_history_and_retrieval():
    """Test GET /api/incidents and GET /api/incidents/{incident_id}."""
    # Create an incident
    post_resp = client.post("/api/incidents", json={"report": "Car crash on Highway 5 with 1 injured."})
    assert post_resp.status_code == 201
    created_id = post_resp.json()["incident_id"]

    # List all incidents
    list_resp = client.get("/api/incidents")
    assert list_resp.status_code == 200
    incidents = list_resp.json()
    assert any(inc["incident_id"] == created_id for inc in incidents)

    # Get single incident
    get_resp = client.get(f"/api/incidents/{created_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["incident_id"] == created_id

    # Non-existent incident
    not_found = client.get("/api/incidents/INC-999999")
    assert not_found.status_code == 404

def test_incident_trace_endpoint():
    """Test GET /api/incidents/{incident_id}/trace."""
    post_resp = client.post("/api/incidents", json={"report": "Chemical leak in laboratory room 402."})
    created_id = post_resp.json()["incident_id"]

    trace_resp = client.get(f"/api/incidents/{created_id}/trace")
    assert trace_resp.status_code == 200
    trace_data = trace_resp.json()
    assert trace_data["incident_id"] == created_id
    assert "agents" in trace_data
    assert "trace" in trace_data
    assert len(trace_data["trace"]) == 6

    # Check that each trace item has agent name, status, duration, and summary
    for item in trace_data["trace"]:
        assert "agent" in item
        assert "status" in item
        assert "duration_ms" in item
        assert "summary" in item

def test_human_review_endpoint():
    """Test POST /api/incidents/{incident_id}/review."""
    post_resp = client.post("/api/incidents", json={"report": "Small brush fire in park."})
    created_id = post_resp.json()["incident_id"]

    # Approve
    review_payload = {
        "decision": "approve",
        "reviewer_notes": "Operator verified with caller. Units can stage.",
        "reviewer_id": "dispatcher_44"
    }
    review_resp = client.post(f"/api/incidents/{created_id}/review", json=review_payload)
    assert review_resp.status_code == 200
    res_json = review_resp.json()
    assert res_json["status"] == "reviewed"
    assert res_json["human_review"]["decision"] == "approve"
    assert res_json["human_review"]["reviewed"] is True
    assert "does NOT constitute official emergency dispatch authorization" in res_json["disclaimer"]

    # Retrieve incident to confirm human_review record is persisted
    get_resp = client.get(f"/api/incidents/{created_id}")
    assert get_resp.json()["human_review"]["decision"] == "approve"
