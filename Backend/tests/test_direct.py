import asyncio
import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.schemas.models import (
    IncidentCreateRequest,
    HumanReviewRequest
)
from app.api.routes import (
    create_incident,
    list_incidents,
    get_incident,
    get_incident_trace,
    review_incident,
    health_check
)
from app.orchestrator.workflow import incident_store

async def run_all_tests():
    print("=" * 60)
    print("RUNNING RESQAI END-TO-END TEST SUITE")
    print("=" * 60)

    # 1. Health check
    print("\n[TEST 1] GET /api/health ...")
    health = await health_check()
    assert health.status == "healthy", f"Health status was {health.status}"
    assert health.available_resources_count >= 10, f"Expected >=10 resources, got {health.available_resources_count}"
    print(f" PASS - Status: {health.status}, Resources: {health.available_resources_count}, Provider: {health.active_provider}")

    # 2. Test Case 1: Flood emergency with injuries (Contract compliance test)
    print("\n[TEST 2] POST /api/incidents - Flood emergency with injuries ...")
    req1 = IncidentCreateRequest(report="Flood near school. Two people injured.")
    res1 = await create_incident(req1)
    d1 = res1.model_dump()

    # Verify contract shape
    assert d1["incident_id"].startswith("INC-"), "Missing or invalid incident_id"
    assert d1["category"] == "Flood", f"Expected category Flood, got {d1['category']}"
    assert d1["priority"] == "Critical", f"Expected priority Critical, got {d1['priority']}"
    assert "school" in d1["location"].lower(), f"Expected school in location, got {d1['location']}"
    assert d1["affected_people"] == 2, f"Expected 2 affected, got {d1['affected_people']}"
    assert d1["injuries_reported"] is True, "Expected injuries_reported to be True"
    assert isinstance(d1["missing_information"], list), "missing_information must be a list"
    assert isinstance(d1["agents"], dict), "agents must be a dict"
    for ag in ["intake", "triage", "resource", "planning", "verification"]:
        assert d1["agents"][ag] == "completed", f"Agent {ag} status is {d1['agents'][ag]}"

    assert len(d1["resources"]) > 0, "Expected matched resources"
    assert len(d1["action_plan"]) > 0, "Expected action plan"
    assert d1["verification"]["status"] == "human_review_required"
    assert d1["verification"]["human_review_required"] is True

    # Check separation of safety guidance from professional action
    action_types = [a["action_type"] for a in d1["action_plan"]]
    assert "safety_guidance" in action_types, "Action plan must contain safety_guidance"
    assert "professional_judgment_action" in action_types, "Action plan must contain professional_judgment_action"
    print(f" PASS - Contract verified! ID: {d1['incident_id']}, Priority: {d1['priority']}, Resources: {len(d1['resources'])}, Actions: {len(d1['action_plan'])}")

    # 3. Test Case 2: Fire emergency
    print("\n[TEST 3] POST /api/incidents - Fire emergency ...")
    req2 = IncidentCreateRequest(report="Fire burning rapidly on 3rd floor of apartment building on Maple Street.")
    res2 = await create_incident(req2)
    d2 = res2.model_dump()
    assert d2["category"] == "Fire", f"Expected Fire, got {d2['category']}"
    assert d2["priority"] in ["Critical", "High"]
    assert any("Fire" in r["resource_type"] or "Hospital" in r["resource_type"] for r in d2["resources"])
    print(f" PASS - Fire parsed, Category: {d2['category']}, Priority: {d2['priority']}")

    # 4. Test Case 3: Vague emergency report with missing location
    print("\n[TEST 4] POST /api/incidents - Vague report with missing location ...")
    req3 = IncidentCreateRequest(report="Help water is rising quickly, people are stuck!")
    res3 = await create_incident(req3)
    d3 = res3.model_dump()
    assert d3["category"] == "Flood"
    missing_str = " ".join(d3["missing_information"]).lower()
    assert "location" in missing_str or "address" in missing_str or "coordinates" in missing_str or d3["location"] == "Unknown / Unspecified"
    flags_str = " ".join(d3["verification"]["flags"])
    assert "LOCATION_UNVERIFIED" in flags_str or "location" in flags_str.lower()
    print(f" PASS - Vague location flagged: {d3['missing_information']}")

    # 5. Test Case 4: Contradictory or incomplete information
    print("\n[TEST 5] POST /api/incidents - Incomplete information ...")
    req4 = IncidentCreateRequest(report="Loud blast heard in area. Unknown if anyone harmed.")
    res4 = await create_incident(req4)
    d4 = res4.model_dump()
    assert len(d4["missing_information"]) > 0
    assert d4["verification"]["status"] == "human_review_required"
    print(f" PASS - Gaps identified. Missing info count: {len(d4['missing_information'])}")

    # 6. Test Case 5: Fallback resilience
    print("\n[TEST 6] Deterministic Fallback Resilience ...")
    from app.orchestrator.workflow import run_incident_orchestrator
    fallback_res = run_incident_orchestrator("Flash flood swept cars on Highway 10. 4 people trapped.")
    assert fallback_res.incident_id.startswith("INC-")
    assert fallback_res.priority in ["Critical", "High"]
    assert fallback_res.affected_people == 4
    for k, v in fallback_res.agents.items():
        assert v == "completed", f"Agent {k} status is {v}"
    print(f" PASS - Fallback pipeline processed incident {fallback_res.incident_id} successfully.")

    # 7. GET /api/incidents & GET /api/incidents/{incident_id}
    print("\n[TEST 7] GET /api/incidents & GET /api/incidents/{id} ...")
    all_incidents = await list_incidents()
    assert len(all_incidents) >= 4, f"Expected >=4 incidents, got {len(all_incidents)}"
    single = await get_incident(res1.incident_id)
    assert single.incident_id == res1.incident_id
    print(f" PASS - Retrieved {len(all_incidents)} incidents from session store.")

    # 8. GET /api/incidents/{incident_id}/trace
    print("\n[TEST 8] GET /api/incidents/{id}/trace ...")
    trace_res = await get_incident_trace(res1.incident_id)
    assert trace_res["incident_id"] == res1.incident_id
    assert len(trace_res["trace"]) == 5, f"Expected 5 agent traces, got {len(trace_res['trace'])}"
    for item in trace_res["trace"]:
        print(f"   - Agent '{item.agent}': status={item.status}, model={item.model}, duration={item.duration_ms}ms")
    print(" PASS - Execution trace verified.")

    # 9. POST /api/incidents/{incident_id}/review
    print("\n[TEST 9] POST /api/incidents/{id}/review ...")
    review_req = HumanReviewRequest(
        decision="approve",
        reviewer_notes="Operator confirmed coordinates. Units standing by.",
        reviewer_id="dispatcher_77"
    )
    review_result = await review_incident(review_req, res1.incident_id)
    assert review_result["status"] == "reviewed"
    assert review_result["human_review"]["decision"] == "approve"
    assert "does NOT constitute official emergency dispatch authorization" in review_result["disclaimer"]
    updated_inc = await get_incident(res1.incident_id)
    assert updated_inc.human_review.decision == "approve"
    print(f" PASS - Human review recorded with non-dispatch disclaimer: {review_result['human_review']['decision']}")

    print("\n" + "=" * 60)
    print("ALL 9 TEST CASES PASSED PERFECTLY!")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(run_all_tests())
