import logging
from typing import Dict, Any, List, Optional, Tuple
from app.schemas.models import IncidentRecord, TriageRecord, ResourceItem, PlanAction, VerificationData

logger = logging.getLogger("resqai.agents.coordination")

def run_coordination_agent(
    record: IncidentRecord,
    triage: TriageRecord,
    resources: List[ResourceItem],
    action_plan: List[PlanAction],
    verification: VerificationData
) -> Tuple[Dict[str, Any], str, Optional[str]]:
    """
    Executes Agent 6 (Coordination Agent).
    Creates simulated dispatch requests for approved rescue plans.
    """
    # Deterministic simulation logic
    # In a real system, this would interact with dispatch APIs.
    # Here, we generate structured audit records for the simulation.

    simulated_requests: Dict[str, Any] = {}

    # 1. Filter actions that require professional judgment
    professional_actions = [a for a in action_plan if a.action_type == "professional_judgment_action"]

    # 2. Simulate dispatch based on required categories
    for action in professional_actions:
        if action.assigned_resource_id:
            category = action.assigned_resource_id.split("-")[1] # e.g. "HOSP" from "RES-HOSP-001"
            simulated_requests[category] = {
                "status": "created_simulated",
                "resource_id": action.assigned_resource_id,
                "step": action.step
            }

    logger.info("Coordination agent created %d simulated dispatch requests", len(simulated_requests))

    return simulated_requests, "deterministic-coordination-engine", None
