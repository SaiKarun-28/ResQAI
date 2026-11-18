import asyncio
import json
import threading
from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest
from fastapi.testclient import TestClient

from app.agents import intake, planning, triage, verification
from app.api import routes
from app.main import app, startup_event
from app.orchestrator import workflow
from app.schemas.models import (
    HumanReviewRequest, IncidentCreateRequest, IncidentRecord, IncidentResponse,
    PlanAction, ResourceItem, TriageRecord,
)
from app.tools import resource_search


def incident_snapshot(incident_id="INC-001"):
    return IncidentResponse(
        incident_id=incident_id, category="Medical", priority="High",
        location="At 123 Main Street", injuries_reported=False,
        missing_information=["Unverified"], agents={"intake": "completed"},
        resources=[{"resource_id": "demo", "evidence": ["original"]}],
        action_plan=[], verification={"flags": ["human review"]},
    )


def test_store_ids_are_unique_under_concurrency():
    store = workflow.IncidentStore()
    with ThreadPoolExecutor(max_workers=16) as pool:
        ids = list(pool.map(lambda _: store.next_incident_id(), range(2000)))
    assert len(set(ids)) == 2000
    assert {int(value.split("-")[1]) for value in ids} == set(range(1, 2001))


def test_store_save_get_list_and_review_are_deep_snapshots():
    store = workflow.IncidentStore()
    original = incident_snapshot()
    store.save(original)
    original.resources[0]["evidence"].append("mutated original")
    original.agents["intake"] = "failed"
    first = store.get("INC-001")
    assert first.resources[0]["evidence"] == ["original"]
    assert first.agents["intake"] == "completed"
    first.resources[0]["evidence"].append("mutated get")
    store.list_all()[0].verification["flags"].clear()
    reviewed = store.record_review("INC-001", HumanReviewRequest(decision="approve"))
    reviewed.human_review.decision = "reject"
    reviewed.resources.clear()
    latest = store.get("INC-001")
    assert latest.resources[0]["evidence"] == ["original"]
    assert latest.verification["flags"] == ["human review"]
    assert latest.human_review.decision == "approve"
    assert store.get("missing") is None
    assert store.record_review("missing", HumanReviewRequest(decision="reject")) is None


def test_concurrent_reviews_never_mix_fields():
    store = workflow.IncidentStore()
    store.save(incident_snapshot())

    def review(index):
        payload = HumanReviewRequest(
            decision="approve" if index % 2 else "reject",
            reviewer_id=str(index), reviewer_notes=f"note-{index}",
        )
        result = store.record_review("INC-001", payload).human_review
        assert result.reviewer_id == str(index)
        assert result.reviewer_notes == f"note-{index}"
        assert result.decision == payload.decision
        assert result.reviewed and result.reviewed_at

    with ThreadPoolExecutor(max_workers=12) as pool:
        list(pool.map(review, range(100)))
    final = store.get("INC-001").human_review
    assert final.reviewer_notes == f"note-{final.reviewer_id}"
    assert final.decision == ("approve" if int(final.reviewer_id) % 2 else "reject")


def test_review_route_uses_atomic_store_method(monkeypatch, offline_isolated_backend):
    store = offline_isolated_backend
    store.save(incident_snapshot())

    def forbidden(*args, **kwargs):
        raise AssertionError("Review must not use get/mutate/save")

    monkeypatch.setattr(store, "get", forbidden)
    monkeypatch.setattr(store, "save", forbidden)
    client = TestClient(app)
    response = client.post("/api/incidents/INC-001/review", json={"decision": "approve", "reviewer_notes": "checked"})
    assert response.status_code == 200
    assert store.list_all()[0].human_review.reviewer_notes == "checked"
    assert client.post("/api/incidents/missing/review", json={"decision": "reject"}).status_code == 404


def test_health_responds_while_synchronous_pipeline_is_blocked(monkeypatch):
    entered, release = threading.Event(), threading.Event()

    def blocked_pipeline(report):
        entered.set()
        if not release.wait(timeout=5):
            raise TimeoutError("Test did not release pipeline")
        return incident_snapshot()

    monkeypatch.setattr(routes, "run_incident_orchestrator", blocked_pipeline)

    async def scenario():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            post = asyncio.create_task(client.post("/api/incidents", json={"report": "Medical emergency"}))
            try:
                assert await asyncio.to_thread(entered.wait, 2)
                assert not post.done(), "Synchronous pipeline blocked the request event loop"
                health = await asyncio.wait_for(client.get("/api/health"), timeout=2)
                assert health.status_code == 200
                assert not post.done(), "Health must finish before the pipeline is released"
            finally:
                release.set()
                result = await post
            assert result.status_code == 201

    asyncio.run(scenario())


@pytest.mark.parametrize("report,category", [
    ("Cardiac arrest at 123 Main Street. One person affected.", "Medical"),
    ("Heart attack in a car on Highway 5.", "Medical"),
    ("Medical emergency on Highway 22.", "Medical"),
    ("Car crash on Highway 5. One person unconscious.", "Traffic Accident"),
    ("Vehicle collision at 99 Main Street.", "Traffic Accident"),
    ("An accident involving two cars at 99 Main Street.", "Traffic Accident"),
    ("A car parked on Highway 5.", "Emergency Incident"),
    ("A cardboard box beside the smokehouse.", "Emergency Incident"),
    ("Flash flood swept cars on Highway 10. 4 people trapped.", "Flood"),
    ("Explosion at 11 Main Street. People trapped.", "Explosion"),
])
def test_word_aware_categories(report, category):
    assert intake.deterministic_intake_fallback(report).category == category


@pytest.mark.parametrize("report,injured", [
    ("Fire burning at 123 Main Street.", False),
    ("No injuries reported.", False),
    ("Nobody is injured.", False),
    ("No one was hurt.", False),
    ("One person is not injured.", False),
    ("No bleeding or injuries.", False),
    ("Injuries were not reported.", False),
    ("Injuries: none.", False),
    ("A person denies injuries.", False),
    ("Fire without injuries.", False),
    ("No injuries reported, but one person is bleeding.", True),
    ("No injuries initially. Two people now injured.", True),
    ("No injuries reported and a person is bleeding.", True),
    ("Nobody injured; however a child has burns.", True),
    ("A person is injured. No bleeding reported.", True),
    ("One person has burns and wounds.", True),
])
def test_injury_negation_is_local_and_burning_is_not_injury(report, injured):
    assert intake.deterministic_intake_fallback(report).injuries_reported is injured


@pytest.mark.parametrize("phrase,count", [
    ("1 person injured", 1), ("one person injured", 1), ("a person injured", 1),
    ("One child trapped", 1), ("an injured person", 1),
    ("2 people affected", 2), ("three victims", 3), ("4 hurt", 4),
])
def test_singular_and_plural_counts(phrase, count):
    assert intake.deterministic_intake_fallback(phrase).affected_people == count


@pytest.mark.parametrize("report,location", [
    ("Fire at 123 Main Street with one person injured.", "At 123 Main Street"),
    ("Crash on Highway 10. 4 people trapped.", "On Highway 10"),
    ("Collision on I-95 near Exit 24 with two people injured.", "On I-95 near Exit 24"),
    ("Flood near school. Two people injured.", "Near school"),
    ("Chemical leak in laboratory room 402.", "In laboratory room 402"),
    ("Fire at 123 Main Street 2 people injured.", "At 123 Main Street"),
    ("One person in cardiac arrest at 123 Main Street.", "At 123 Main Street"),
])
def test_location_retains_addresses_and_highway_numbers(report, location):
    record = intake.deterministic_intake_fallback(report)
    assert record.location == location
    assert intake.LOCATION_WARNING in record.missing_information


def test_missing_location_warning_survives_fallback_and_model(monkeypatch):
    report = "Help water is rising quickly, people stuck!"
    fallback = intake.deterministic_intake_fallback(report)
    assert fallback.location == "Unknown / Unspecified"
    assert "Precise address or GPS coordinates missing" in fallback.missing_information
    monkeypatch.setattr(intake, "call_llm_json", lambda **kwargs: (IncidentRecord(location="Invented street"), "stub", None))
    record, _, _ = intake.run_intake_agent(report)
    assert "Precise address or GPS coordinates missing" in record.missing_information
    assert intake.LOCATION_WARNING in record.missing_information


@pytest.mark.parametrize("report,priority,hazard", [
    ("One person in cardiac arrest at 123 Main Street.", "Critical", "Reported life threat: cardiac arrest"),
    ("Heart attack on Highway 7.", "Critical", "Reported life threat: heart attack"),
    ("One person is not breathing.", "Critical", "Reported life threat: absent or abnormal breathing"),
    ("A person is unconscious.", "Critical", "Reported life threat: unconscious or unresponsive person"),
    ("A child has severe bleeding.", "Critical", "Reported life threat: severe bleeding"),
    ("Explosion at warehouse. Two people trapped.", "Critical", "Reported people trapped"),
    ("Explosion heard nearby.", "High", "Reported explosion hazard"),
    ("A person trapped in an elevator.", "High", "Reported people trapped"),
])
def test_explicit_threats_drive_triage_and_model_priority_floor(monkeypatch, report, priority, hazard):
    record = intake.deterministic_intake_fallback(report)
    assert hazard in record.hazards
    assert triage.deterministic_triage_fallback(record).priority == priority
    monkeypatch.setattr(triage, "call_llm_json", lambda **kwargs: (TriageRecord(priority="Low", reasoning="stub"), "stub", None))
    assessment, _, _ = triage.run_triage_agent(record)
    assert assessment.priority == priority
    assert "Provisional" in assessment.disclaimer


def test_medical_uncertainty_and_negated_trapping():
    record = intake.deterministic_intake_fallback("Medical emergency. No injuries. Nobody trapped.")
    assessment = triage.deterministic_triage_fallback(record)
    assert "Reported people trapped" not in record.hazards
    assert not any(h.startswith("Reported life threat:") for h in record.hazards)
    assert assessment.priority == "High"
    assert any("Medical acuity" in flag for flag in assessment.uncertainty_flags)
    flood = intake.deterministic_intake_fallback("Flood near school. No people trapped, no injuries.")
    assert "Reported people trapped" not in flood.hazards
    assert triage.deterministic_triage_fallback(flood).priority == "High"


def resource_action(resource_id):
    return PlanAction(step=1, action="Review resource", action_type="professional_judgment_action", rationale="Test", target="Operator", assigned_resource_id=resource_id)


def audit(resources, actions=None, location="At 123 Main Street"):
    return verification.run_verification_agent(
        IncidentRecord(location=location), TriageRecord(priority="High", reasoning="Test"),
        resources, actions or [],
    )[0]


@pytest.mark.parametrize("field", ["name", "resource_type", "location", "description", "source", "last_updated", "availability_status"])
def test_known_resource_id_with_tampered_fields_is_not_verified(field):
    resource = ResourceItem.model_validate(resource_search.load_resources()[0])
    setattr(resource, field, "tampered")
    result = audit([resource], [resource_action(resource.resource_id)])
    assert resource.resource_id not in result.verified_resource_ids
    assert any("canonical" in claim for claim in result.unsupported_claims)
    assert any("not matched and verified" in flag for flag in result.flags)


def test_canonical_resources_allow_retrieval_annotations_but_not_conflicting_duplicates():
    resource = ResourceItem.model_validate(resource_search.load_resources()[0])
    resource.match_reason = "New match reasoning"
    resource.evidence = ["New matching evidence"]
    assert audit([resource]).verified_resource_ids == [resource.resource_id]
    tampered = resource.model_copy(update={"name": "Tampered"})
    assert audit([resource, tampered]).verified_resource_ids == []


def test_unmatched_action_ids_and_unknown_resources_are_flagged():
    canonical_id = resource_search.load_resources()[0]["resource_id"]
    result = audit([], [resource_action(canonical_id), resource_action("RES-UNKNOWN")])
    assert sum("not matched and verified" in flag for flag in result.flags) == 2
    assert any("RES-UNKNOWN" in claim for claim in result.unsupported_claims)
    unknown = ResourceItem.model_validate(resource_search.load_resources()[0])
    unknown.resource_id = "RES-UNKNOWN"
    assert audit([unknown]).verified_resource_ids == []
    assert audit([unknown]).unsupported_claims


@pytest.mark.parametrize("location", ["At 123 Main Street", "Unknown / Unspecified", "Near school"])
def test_all_reported_locations_remain_unverified(location):
    result = audit([], location=location)
    assert any(flag.startswith("LOCATION_UNVERIFIED:") for flag in result.flags)
    assert result.human_review_required
    assert result.status == "human_review_required"
    assert any("human operator verification mandatory" in flag for flag in result.flags)


def test_planning_prompt_contains_grounding_metadata(monkeypatch):
    resources = resource_search.search_resources("Medical")
    captured = {}

    def capture(**kwargs):
        captured.update(kwargs)
        return None, "stub", "offline"

    monkeypatch.setattr(planning, "call_llm_json", capture)
    planning.run_planning_agent(IncidentRecord(), TriageRecord(reasoning="Test"), resources)
    serialized = captured["prompt"].split("Retrieved Grounded Resources:\n", 1)[1].split("\n\nReturn JSON", 1)[0]
    grounded = json.loads(serialized)
    for original, supplied in zip(resources, grounded):
        for field in ("description", "source", "availability_status", "last_updated"):
            assert supplied[field] == getattr(original, field)


def test_resource_cache_returns_isolated_snapshots():
    first = resource_search.load_resources()
    resource_id = first[0]["resource_id"]
    first[0]["name"] = "tampered"
    first[0]["evidence"].append("tampered")
    first.clear()
    second = resource_search.load_resources()
    assert second[0]["name"] != "tampered"
    assert second[0]["evidence"] == []
    resource_search.get_resource_by_id(resource_id)["description"] = "tampered"
    assert resource_search.get_resource_by_id(resource_id)["description"] != "tampered"


@pytest.mark.parametrize("failure", ["missing", "malformed", "empty", "object", "duplicate", "schema", "empty_id"])
def test_bad_dataset_fails_clearly_and_recovers_without_restart(monkeypatch, tmp_path, failure):
    valid = resource_search.load_resources()
    dataset = tmp_path / "resources.json"
    invalid = {
        "malformed": "{bad json", "empty": "[]", "object": "{}",
        "duplicate": json.dumps([valid[0], valid[0]]),
        "schema": json.dumps([{"resource_id": "only-id"}]),
        "empty_id": json.dumps([dict(valid[0], resource_id=" ")]),
    }
    if failure != "missing":
        dataset.write_text(invalid[failure], encoding="utf-8")
    monkeypatch.setattr(resource_search, "RESOURCES_FILE_PATH", dataset)
    monkeypatch.setattr(resource_search, "_RESOURCES_CACHE", None)
    with pytest.raises(resource_search.ResourceDatasetError, match="dataset is unavailable or invalid"):
        resource_search.load_resources()
    assert resource_search._RESOURCES_CACHE is None
    response = TestClient(app).get("/api/health")
    assert response.status_code == 503
    assert "degraded" in response.json()["detail"]
    assert str(dataset) not in response.text
    dataset.write_text(json.dumps(valid), encoding="utf-8")
    assert resource_search.load_resources() == valid
    assert TestClient(app).get("/api/health").status_code == 200


def test_startup_reports_degraded_dataset_and_allows_recovery(monkeypatch, tmp_path, caplog):
    valid = resource_search.load_resources()
    dataset = tmp_path / "resources.json"
    dataset.write_text("[]", encoding="utf-8")
    monkeypatch.setattr(resource_search, "RESOURCES_FILE_PATH", dataset)
    monkeypatch.setattr(resource_search, "_RESOURCES_CACHE", None)
    with caplog.at_level("INFO"):
        asyncio.run(startup_event())
    assert "started in degraded mode" in caplog.text
    assert "started successfully" not in caplog.text
    response = TestClient(app).post("/api/incidents", json={"report": "Flood near school"})
    assert response.status_code == 201
    assert response.json()["agents"]["resource"] == "failed"
    assert response.json()["agents"]["verification"] == "failed"
    assert response.json()["verification"]["human_review_required"]
    assert any(flag.startswith("LOCATION_UNVERIFIED:") for flag in response.json()["verification"]["flags"])
    dataset.write_text(json.dumps(valid), encoding="utf-8")
    assert TestClient(app).get("/api/health").status_code == 200


def test_http_error_does_not_expose_internal_exception(monkeypatch):
    def broken(report):
        raise RuntimeError("private-diagnostic-marker")

    monkeypatch.setattr(routes, "run_incident_orchestrator", broken)
    response = TestClient(app).post("/api/incidents", json={"report": "Help"})
    assert response.status_code == 500
    assert response.json()["detail"] == "Internal error processing incident pipeline."
    assert "private-diagnostic-marker" not in response.text


@pytest.mark.parametrize("agent", ["intake", "triage", "resource", "planning", "verification"])
def test_agent_failure_traces_do_not_expose_internal_exception(monkeypatch, agent):
    def broken(*args, **kwargs):
        raise RuntimeError("private-diagnostic-marker")

    monkeypatch.setattr(workflow, f"run_{agent}_agent", broken)
    response = TestClient(app).post("/api/incidents", json={"report": "Flood near school"})
    assert response.status_code == 201
    assert response.json()["agents"][agent] == "failed"
    assert "private-diagnostic-marker" not in response.text


def test_resource_failure_return_does_not_expose_internal_exception(monkeypatch):
    monkeypatch.setattr(workflow, "run_resource_agent", lambda *args: ([], "stub", "private-diagnostic-marker"))
    response = TestClient(app).post("/api/incidents", json={"report": "Flood near school"})
    assert response.status_code == 201
    assert "private-diagnostic-marker" not in response.text


@pytest.mark.parametrize("report", ["", "   ", "\n\t\r", "x" * 10001])
def test_report_validation_rejects_blank_and_oversized_input(report):
    response = TestClient(app).post("/api/incidents", json={"report": report})
    assert response.status_code == 422


def test_report_validation_trims_and_publishes_max_length():
    assert IncidentCreateRequest(report=" \n Help \t ").report == "Help"
    assert len(IncidentCreateRequest(report="x" * 10000).report) == 10000
    schema = app.openapi()["components"]["schemas"]["IncidentCreateRequest"]
    assert schema["properties"]["report"]["maxLength"] == 10000
    response = TestClient(app).post("/api/incidents", json={"report": "  Help \n"})
    assert response.status_code == 201
    assert response.json()["raw_report"] == "Help"


def test_application_lifespan_initializes_resources(caplog):
    with caplog.at_level("INFO"):
        with TestClient(app) as client:
            assert client.get("/api/health").status_code == 200
    assert "started successfully" in caplog.text


def test_default_tests_are_offline_and_store_is_empty(offline_isolated_backend):
    from app.tools import llm_client
    assert not llm_client.GEMINI_API_KEY and not llm_client.GROQ_API_KEY
    assert offline_isolated_backend.list_all() == []
    response = TestClient(app).get("/api/health")
    assert response.json()["active_provider"] == "deterministic_fallback"
