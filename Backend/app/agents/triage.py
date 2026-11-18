import logging
from typing import Tuple, Optional, List
from app.schemas.models import IncidentRecord, TriageRecord
from app.tools.llm_client import call_llm_json

logger = logging.getLogger("resqai.agents.triage")

SYSTEM_PROMPT = """You are Agent 2 (Triage Agent) in ResQAI, an emergency intelligence decision-support prototype.
Your role:
- Assess the extracted IncidentRecord.
- Identify potential urgency indicators (e.g., active dynamic hazard, reported injuries, vulnerable population).
- Assign a provisional priority: 'Critical', 'High', 'Medium', or 'Low'.
- Detail clear reasoning explaining the provisional priority.
- Identify missing information that introduces uncertainty into triage.
- Flag uncertainty prominently.
- IMPORTANT DISCLAIMER: Do NOT represent this provisional AI rating as an official emergency dispatch classification.
Respond strictly in JSON matching the schema."""

TRIAGE_SCHEMA_PROMPT = """Perform provisional triage on this incident record:
Category: {category}
Location: {location}
Affected People: {affected_people}
Injuries Reported: {injuries_reported}
Hazards: {hazards}
Missing Information: {missing_info}

Return JSON matching this exact structure:
{{
  "priority": "Critical" | "High" | "Medium" | "Low",
  "reasoning": "detailed explanation of rationale",
  "urgency_indicators": ["list of urgency factors"],
  "uncertainty_flags": ["list of uncertainty caveats"],
  "missing_information": ["missing info affecting triage"],
  "disclaimer": "Provisional AI assessment only; not an official emergency severity classification."
}}"""

def deterministic_triage_fallback(record: IncidentRecord) -> TriageRecord:
    """
    Deterministic rule-based triage assessment.
    Provides clear risk stratification without over-claiming certainty.
    """
    urgency_indicators: List[str] = []
    uncertainty_flags: List[str] = []
    missing_for_triage: List[str] = list(record.missing_information)

    # Evaluate urgency indicators
    if record.injuries_reported:
        urgency_indicators.append("Direct physical casualties/injuries reported")
    if record.category in ["Flood", "Fire", "Hazmat", "Building Collapse"]:
        urgency_indicators.append(f"Dynamic high-risk hazard environment ({record.category})")
    if record.affected_people and record.affected_people > 1:
        urgency_indicators.append(f"Multiple affected individuals ({record.affected_people} reported)")
    if "school" in record.location.lower() or "hospital" in record.location.lower() or "child" in str(record.hazards).lower():
        urgency_indicators.append("Proximity to vulnerable population or critical infrastructure")

    # Evaluate uncertainty flags
    if record.category == "Medical":
        uncertainty_flags.append("Medical acuity is unverified; absence of reported injuries does not exclude a life threat")
    if record.affected_people is None:
        uncertainty_flags.append("Total casualty count is unverified; priority may escalate if trapped persons are confirmed")
    if record.location == "Unknown / Unspecified" or len(record.location.split()) <= 2:
        uncertainty_flags.append("Vague location complicates rapid responder deployment and ground verification")
    if record.injuries_reported and any("severity" in m.lower() for m in record.missing_information):
        uncertainty_flags.append("Injury acuity (life-threatening vs minor) is unconfirmed")

    # Only explicit extracted threats escalate here, not speculative entrapment.
    life_threats = [hazard for hazard in record.hazards if hazard.startswith("Reported life threat:")]
    trapped = "Reported people trapped" in record.hazards
    dynamic_categories = ["Flood", "Fire", "Hazmat", "Building Collapse", "Explosion", "Earthquake"]
    urgency_indicators.extend(life_threats)
    if trapped:
        urgency_indicators.append("People reported trapped; rescue needs urgent verification")

    # Determine provisional priority without treating absent injury details as safety.
    if life_threats or (trapped and record.category in dynamic_categories):
        priority = "Critical"
        reasoning = (
            "Provisional CRITICAL priority assigned from reported life-threatening symptoms "
            "or people trapped in an active hazard. These reports require urgent human verification."
        )
    elif record.injuries_reported and (record.category in dynamic_categories or (record.affected_people and record.affected_people >= 2)):
        priority = "Critical"
        reasoning = (
            f"Provisional CRITICAL priority assigned: Reported {record.category.lower()} with reported "
            f"injuries ({record.affected_people or 'unspecified count'} affected). Active environmental hazard "
            f"presents immediate threat to life safety."
        )
    elif record.injuries_reported or trapped or record.category in ["Fire", "Flood", "Hazmat", "Explosion", "Building Collapse", "Medical"]:
        priority = "High"
        reasoning = (
            f"Provisional HIGH priority assigned: Threat environment involves {record.category.lower()} "
            f"or reported injuries, requiring urgent resource staging and rapid verification."
        )
    elif record.category in ["Traffic Accident", "Storm", "Earthquake"]:
        priority = "Medium"
        reasoning = (
            f"Provisional MEDIUM priority assigned: {record.category} incident reported without confirmed "
            f"life-threatening injuries, but environmental or structural hazards require operational monitoring."
        )
    else:
        priority = "Low"
        reasoning = (
            "Provisional LOW priority assigned: No life-safety threats or acute hazards detected in available report."
        )

    return TriageRecord(
        priority=priority,
        reasoning=reasoning,
        urgency_indicators=urgency_indicators,
        uncertainty_flags=uncertainty_flags,
        missing_information=missing_for_triage,
        disclaimer="Provisional AI assessment only; not an official emergency severity classification."
    )

def run_triage_agent(record: IncidentRecord) -> Tuple[TriageRecord, str, Optional[str]]:
    """
    Executes Agent 2 (Triage Agent).
    Attempts LLM first; if unavailable, uses deterministic fallback.
    Returns: (TriageRecord, model_used, error_message)
    """
    prompt = TRIAGE_SCHEMA_PROMPT.format(
        category=record.category,
        location=record.location,
        affected_people=record.affected_people,
        injuries_reported=record.injuries_reported,
        hazards=record.hazards,
        missing_info=record.missing_information
    )

    parsed_triage, model_used, error_msg = call_llm_json(
        prompt=prompt,
        schema_cls=TriageRecord,
        system_prompt=SYSTEM_PROMPT
    )

    if parsed_triage:
        # A model response must not downgrade explicit threats or medical uncertainty.
        safety_assessment = deterministic_triage_fallback(record)
        ranks = {"Low": 0, "Medium": 1, "High": 2, "Critical": 3}
        explicit_threat = any(h.startswith("Reported life threat:") or h == "Reported people trapped" for h in record.hazards)
        if (explicit_threat or record.category in ["Medical", "Explosion"]) and ranks[parsed_triage.priority] < ranks[safety_assessment.priority]:
            parsed_triage.priority = safety_assessment.priority
            parsed_triage.reasoning = safety_assessment.reasoning
            parsed_triage.urgency_indicators = list(dict.fromkeys(parsed_triage.urgency_indicators + safety_assessment.urgency_indicators))
            parsed_triage.uncertainty_flags.append("Priority floor applied to reported threats; human assessment required")
        # Guarantee mandatory disclaimer is present
        parsed_triage.disclaimer = "Provisional AI assessment only; not an official emergency severity classification."
        logger.info(f"Triage agent succeeded using {model_used}")
        return parsed_triage, model_used, None

    fallback_triage = deterministic_triage_fallback(record)
    logger.info("Triage agent executed deterministic fallback")
    return fallback_triage, "deterministic-triage-engine", error_msg
