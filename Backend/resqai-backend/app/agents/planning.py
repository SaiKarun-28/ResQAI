import json
import logging
from typing import List, Tuple, Optional
from pydantic import BaseModel
from app.schemas.models import IncidentRecord, TriageRecord, ResourceItem, PlanAction
from app.tools.llm_client import call_llm_json

logger = logging.getLogger("resqai.agents.planning")

class PlanActionList(BaseModel):
    actions: List[PlanAction]

SYSTEM_PROMPT = """You are Agent 4 (Planning Agent) in ResQAI, an emergency intelligence decision-support prototype.
Your role:
- Generate an ordered, sequential response action plan based on extracted facts, provisional triage, and retrieved resources.
- Clearly separate 'safety_guidance' (advisories for affected public) from 'professional_judgment_action' (actions requiring trained responder authorization).
- Provide a clear rationale for every recommended action.
- Reference retrieved resource IDs (e.g. RES-HOSP-001, RES-BOAT-001) wherever applicable.
- DO NOT invent resource IDs not present in the provided list.
- DO NOT authorize autonomous dispatch; all professional actions are advisory recommendations.
Respond strictly in JSON matching the schema."""

PLANNING_SCHEMA_PROMPT = """Create an ordered response action plan for this incident:
Incident:
- Category: {category}
- Location: {location}
- Affected People: {affected_people}
- Injuries Reported: {injuries_reported}
- Hazards: {hazards}
- Priority: {priority}

Retrieved Grounded Resources:
{resources_json}

Return JSON with this exact structure:
{{
  "actions": [
    {{
      "step": 1,
      "action": "clear operational or safety instruction",
      "action_type": "safety_guidance" or "professional_judgment_action",
      "rationale": "why this action is recommended",
      "assigned_resource_id": "RES-XXX-000" or null,
      "target": "Public" or "EMS" or "Rescue Team" or "Incident Commander"
    }}
  ]
}}"""

def deterministic_planning_fallback(
    record: IncidentRecord,
    triage: TriageRecord,
    resources: List[ResourceItem]
) -> List[PlanAction]:
    """
    Deterministic rule-based planning engine.
    Ensures structured, ordered guidance separating public safety guidance from professional responder actions.
    """
    actions: List[PlanAction] = []
    step_num = 1

    # Map available resource types
    resource_by_type = {}
    for r in resources:
        resource_by_type.setdefault(r.resource_type, []).append(r)

    # 1. Immediate Public Safety Guidance
    if record.category.lower() == "flood":
        actions.append(PlanAction(
            step=step_num,
            action="Advise individuals near the flood zone to seek higher elevation immediately and strictly avoid walking or driving through moving water.",
            action_type="safety_guidance",
            rationale="Moving floodwaters present immediate risk of drowning and vehicle loss; rapid vertical evacuation preserves life prior to team arrival.",
            assigned_resource_id=None,
            target="Public / Affected Individuals"
        ))
        step_num += 1
    elif record.category.lower() == "fire":
        actions.append(PlanAction(
            step=step_num,
            action="Instruct building occupants to evacuate via nearest unblocked exit, stay low under smoke, and assemble at designated exterior muster points.",
            action_type="safety_guidance",
            rationale="Smoke inhalation and rapid flame spread are primary life threats in structural and brush fires.",
            assigned_resource_id=None,
            target="Public / Occupants"
        ))
        step_num += 1
    elif record.category.lower() == "hazmat":
        actions.append(PlanAction(
            step=step_num,
            action="Instruct individuals upwind and uphill to shelter-in-place, seal doors/windows, and shut down HVAC systems.",
            action_type="safety_guidance",
            rationale="Prevents toxic vapor inhalation during chemical or gas containment efforts.",
            assigned_resource_id=None,
            target="Public / Nearby Residents"
        ))
        step_num += 1
    else:
        actions.append(PlanAction(
            step=step_num,
            action="Establish a safe perimeter and instruct non-involved civilians to clear access routes for emergency vehicles.",
            action_type="safety_guidance",
            rationale="Keeps civilian bystanders safe from secondary impacts and leaves access corridors open.",
            assigned_resource_id=None,
            target="Public / Bystanders"
        ))
        step_num += 1

    # 2. Specialized Responder Action (Rescue / Fire / Hazmat)
    if record.category.lower() == "flood":
        boat_res = resource_by_type.get("Water Rescue", [None])[0]
        res_id = boat_res.resource_id if boat_res else None
        res_name = boat_res.name if boat_res else "Certified Swiftwater Unit"
        actions.append(PlanAction(
            step=step_num,
            action=f"Recommend deployment of motorized swiftwater extraction units from {res_name} to secure and extract trapped individuals.",
            action_type="professional_judgment_action",
            rationale="Specialized watercraft and swiftwater technicians are required to safely negotiate moving water obstacles.",
            assigned_resource_id=res_id,
            target="Rescue Operations Command"
        ))
        step_num += 1
    elif record.category.lower() == "fire":
        fire_res = resource_by_type.get("Fire & Rescue", [None])[0]
        res_id = fire_res.resource_id if fire_res else None
        res_name = fire_res.name if fire_res else "Fire Engine Company"
        actions.append(PlanAction(
            step=step_num,
            action=f"Recommend staging suppression apparatus and search lines from {res_name} for fire attack and secondary search.",
            action_type="professional_judgment_action",
            rationale="Rapid fire suppression limits structural degradation and protects surrounding assets.",
            assigned_resource_id=res_id,
            target="Fire Operations Command"
        ))
        step_num += 1
    elif record.category.lower() == "hazmat":
        haz_res = resource_by_type.get("Hazmat", [None])[0]
        res_id = haz_res.resource_id if haz_res else None
        res_name = haz_res.name if haz_res else "Hazmat Response Team"
        actions.append(PlanAction(
            step=step_num,
            action=f"Recommend staging Level A/B hazmat containment team from {res_name} with atmospheric gas monitors.",
            action_type="professional_judgment_action",
            rationale="Certified hazmat equipment is mandatory before entry into unverified toxic chemical zones.",
            assigned_resource_id=res_id,
            target="Hazmat Operations Commander"
        ))
        step_num += 1

    # 3. Medical Triage and Casualty Management
    if record.injuries_reported or triage.priority in ["Critical", "High"]:
        hosp_res = resource_by_type.get("Hospital", [None])[0]
        med_res = resource_by_type.get("Mobile Medical", [None])[0]
        target_res = hosp_res or med_res
        res_id = target_res.resource_id if target_res else None
        res_name = target_res.name if target_res else "Designated Emergency Medical Facility"
        actions.append(PlanAction(
            step=step_num,
            action=f"Alert trauma and emergency intake staff at {res_name} to prepare for incoming casualties with provisional priority {triage.priority}.",
            action_type="professional_judgment_action",
            rationale="Pre-arrival notification enables surgical teams and trauma bays to be mobilized without transit delay.",
            assigned_resource_id=res_id,
            target="Emergency Medical Services (EMS)"
        ))
        step_num += 1

    # 4. Evacuation & Shelter Staging
    shelter_res = resource_by_type.get("Shelter", [None])[0]
    if shelter_res:
        actions.append(PlanAction(
            step=step_num,
            action=f"Direct displaced or evacuated individuals to {shelter_res.name} ({shelter_res.location}).",
            action_type="safety_guidance",
            rationale="Provides immediate dry shelter, potable water, and first aid for displaced community members.",
            assigned_resource_id=shelter_res.resource_id,
            target="Evacuation Coordinators & Public"
        ))
        step_num += 1

    # 5. Incident Verification and Operations Review
    actions.append(PlanAction(
        step=step_num,
        action="Establish on-scene command post, confirm victim counts, and await human operator verification before executing dispatch actions.",
        action_type="professional_judgment_action",
        rationale="Mandatory protocol requiring on-site reconnaissance to resolve information gaps and verify AI decision support recommendations.",
        assigned_resource_id=None,
        target="Incident Commander / Human Dispatcher"
    ))

    return actions

def run_planning_agent(
    record: IncidentRecord,
    triage: TriageRecord,
    resources: List[ResourceItem]
) -> Tuple[List[PlanAction], str, Optional[str]]:
    """
    Executes Agent 4 (Planning Agent).
    Generates ordered response plan, distinguishing safety guidance from responder actions.
    """
    resources_summary = [
        {
            "resource_id": r.resource_id,
            "name": r.name,
            "type": r.resource_type,
            "location": r.location,
            "description": r.description,
            "source": r.source,
            "availability_status": r.availability_status,
            "last_updated": r.last_updated,
        }
        for r in resources
    ]
    prompt = PLANNING_SCHEMA_PROMPT.format(
        category=record.category,
        location=record.location,
        affected_people=record.affected_people,
        injuries_reported=record.injuries_reported,
        hazards=record.hazards,
        priority=triage.priority,
        resources_json=json.dumps(resources_summary, indent=2)
    )

    parsed_result, model_used, error_msg = call_llm_json(
        prompt=prompt,
        schema_cls=PlanActionList,
        system_prompt=SYSTEM_PROMPT
    )

    if parsed_result and parsed_result.actions:
        logger.info(f"Planning agent succeeded using {model_used} with {len(parsed_result.actions)} actions")
        return parsed_result.actions, model_used, None

    fallback_plan = deterministic_planning_fallback(record, triage, resources)
    logger.info("Planning agent executed deterministic fallback")
    return fallback_plan, "deterministic-planning-engine", error_msg
