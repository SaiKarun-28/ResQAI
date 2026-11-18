import re
import logging
from typing import Tuple, Optional, List
from app.schemas.models import IncidentRecord
from app.tools.llm_client import call_llm_json

logger = logging.getLogger("resqai.agents.intake")

SYSTEM_PROMPT = """You are Agent 1 (Intake Agent) in ResQAI, an emergency intelligence decision-support prototype.
Your role:
- Analyze the emergency report carefully.
- Extract incident category (e.g. Flood, Fire, Medical, Hazmat, Earthquake, Traffic Accident, Storm, Building Collapse).
- Extract location information explicitly stated.
- Identify affected people count (integer or null if unknown).
- Identify reported injuries (boolean), respecting explicit negation.
- Identify reported hazards (including trapped people and life-threatening medical symptoms).
- Reported locations are not independently verified and require human confirmation.
- Identify missing critical information (e.g. exact address, number of trapped people, severity of injuries).
- CRITICAL: Never invent or assume missing details. If unknown, state as unknown or list in missing_information.
Respond strictly in JSON matching the schema."""

INTAKE_SCHEMA_PROMPT = """Extract the structured incident record from this report:
"{report}"

Return JSON matching this exact structure:
{{
  "category": "string (e.g. Flood, Fire, Medical)",
  "location": "string (explicitly stated or 'Unknown / Unspecified')",
  "affected_people": integer or null,
  "injuries_reported": boolean,
  "hazards": ["list of strings"],
  "missing_information": ["list of critical missing details"],
  "notes": "string summary"
}}"""

NUMBER_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "a": 1, "an": 1,
}
COUNT_PATTERN = r"(?:\d+|" + "|".join(NUMBER_WORDS) + r")"
PEOPLE_PATTERN = r"(?:people|persons?|victims?|casualties|individuals?|residents?|kids?|students?|children|child|patients?|men|man|women|woman|occupants?|workers?)"
LOCATION_WARNING = "Reported location is unverified; human address confirmation required"


def _reported(text: str, pattern: str) -> bool:
    """Limited clause-local negation heuristic, not a general language parser."""
    for match in re.finditer(pattern, text, re.IGNORECASE):
        prefix = re.split(
            r"[.;,!?\n]|\b(?:but|however|yet|then)\b|"
            r"\band\s+(?=(?:" + COUNT_PATTERN + r"|another|someone|he|she|they|the)\b)",
            text[:match.start()], flags=re.IGNORECASE,
        )[-1]
        denied = re.search(
            r"\b(?:no|not|without|denies|denied|neither|nobody|none|zero|0|free of|negative for)\b(?:\W+\w+){0,5}\W*$",
            prefix, re.IGNORECASE,
        )
        denied_after = re.match(
            r"\s*(?:(?:are|were|is|was|reported)\s+)*(?:not\b|denied\b|absent\b|:\s*(?:none|no|0)\b)",
            text[match.end():], re.IGNORECASE,
        )
        if not denied and not denied_after:
            return True
    return False


def deterministic_intake_fallback(report: str) -> IncidentRecord:
    """Extract limited explicit evidence; ambiguous reports still need human review."""
    text = report.strip()
    text_lower = text.lower()
    injuries_reported = _reported(
        text_lower,
        r"\b(?:injur(?:y|ies|ed)|casualt(?:y|ies)|hurt|harmed|bleeding|burns?|burned|burnt|wounds?|wounded|unconscious|fatalit(?:y|ies))\b",
    )
    life_threat_patterns = {
        "cardiac arrest": r"\bcardiac arrest\b",
        "heart attack": r"\bheart attack\b",
        "absent or abnormal breathing": r"\b(?:not breathing|isn't breathing|is not breathing|cannot breathe|can't breathe|unable to breathe|stopped breathing|no pulse|not responsive)\b",
        "unconscious or unresponsive person": r"\b(?:unconscious|unresponsive)\b",
        "severe bleeding": r"\b(?:severe|heavy|uncontrolled|profuse) bleeding\b|\bbleeding (?:heavily|profusely|uncontrollably)\b",
        "drowning": r"\bdrowning\b",
        "stroke": r"\bstroke\b",
    }
    hazards = [
        f"Reported life threat: {label}"
        for label, pattern in life_threat_patterns.items() if _reported(text_lower, pattern)
    ]
    medical = _reported(text_lower, r"\b(?:cardiac|stroke|seizures?|unconscious|unresponsive|medical|heart attack|chest pain)\b")
    collision = _reported(text_lower, r"\b(?:crash(?:ed)?|collisions?|pileup|traffic accident|car accident|vehicle accident)\b") or (
        _reported(text_lower, r"\baccident\b")
        and bool(re.search(r"\b(?:cars?|vehicles?|trucks?|buses|bus|motorcycles?|highway|road)\b", text_lower))
    )
    flood = _reported(text_lower, r"\b(?:flood(?:ing|waters)?|submerged|overflow(?:ing)?|drowning)\b") or (
        bool(re.search(r"\bwater\b", text_lower))
        and _reported(text_lower, r"\b(?:rising|rose|deep|stuck|trapped|overflow|rescue)\b")
    )
    fire = _reported(text_lower, r"\b(?:fire|smoke|burning|blaze|flames)\b")
    explosion = _reported(text_lower, r"\b(?:explosions?|blast|detonation)\b")
    hazmat = _reported(text_lower, r"\b(?:chemical|gas leak|toxic|spill|hazmat|fumes)\b")
    collapse = _reported(text_lower, r"\b(?:collapse|collapsed|rubble)\b")

    # A car/highway mention alone is not collision evidence.
    if collision:
        category = "Traffic Accident"
    elif medical and hazards:
        category = "Medical"
    elif flood:
        category = "Flood"
    elif explosion:
        category = "Explosion"
    elif fire:
        category = "Fire"
    elif hazmat:
        category = "Hazmat"
    elif _reported(text_lower, r"\b(?:earthquake|tremor|aftershock)\b"):
        category = "Earthquake"
    elif collapse:
        category = "Building Collapse"
    elif medical or hazards:
        category = "Medical"
    else:
        category = "Emergency Incident"

    count_match = re.search(
        rf"\b({COUNT_PATTERN})\s+(?:(?:injured|trapped|unconscious|affected)\s+)?(?:{PEOPLE_PATTERN}|injured|hurt|dead)\b",
        text_lower,
    )
    affected_people = None
    if count_match:
        value = count_match.group(1)
        affected_people = int(value) if value.isdigit() else NUMBER_WORDS[value]

    # Stop at an incident clause or people count, not arbitrary address digits.
    location = "Unknown / Unspecified"
    location_pattern = (
        r"\b(near|at|on|in|around|by)\s+(?!(?:cardiac arrest|shock|pain|danger|fire|critical condition)\b)(\S.*?)"
        r"(?=$|[.!?;,\n]|\s+\b(?:and|with|where|but|is|are|was|were|has|have)\b|"
        rf"\s+\b{COUNT_PATTERN}\s+(?:{PEOPLE_PATTERN}|injured|hurt)\b)"
    )
    for loc_match in re.finditer(location_pattern, text, re.IGNORECASE):
        candidate = loc_match.group(2).strip()
        if len(candidate) < 3 or candidate.lower() in {"the", "some", "cardiac arrest", "shock", "pain", "danger"}:
            continue
        location = f"{loc_match.group(1).capitalize()} {candidate}"
        break

    if _reported(text_lower, r"\b(?:trapped|entrapped|stuck)\b"):
        hazards.append("Reported people trapped")
    if flood:
        hazards.append("Reported floodwater hazard")
    if fire:
        hazards.append("Reported fire / smoke inhalation hazard")
    if explosion:
        hazards.append("Reported explosion hazard")
    if hazmat:
        hazards.append("Reported chemical / hazardous inhalation risk")
    if collapse:
        hazards.append("Reported unstable debris / structural collapse hazard")
    if not hazards:
        hazards.append("Unverified environmental conditions")

    missing_info: List[str] = []
    if location == "Unknown / Unspecified":
        missing_info.append("Precise address or GPS coordinates missing")
    missing_info.append(LOCATION_WARNING)
    if affected_people is None:
        missing_info.append("Total count of affected or trapped individuals unspecified")
    if injuries_reported:
        missing_info.append("Specific severity and nature of reported injuries unspecified")
    missing_info.append("Reporting party identity and callback contact not established")

    return IncidentRecord(
        category=category,
        location=location,
        affected_people=affected_people,
        injuries_reported=injuries_reported,
        hazards=hazards,
        missing_information=missing_info,
        notes=f"Rule-based extraction for category {category}; wording and negation may require human correction.",
    )

def run_intake_agent(report: str) -> Tuple[IncidentRecord, str, Optional[str]]:
    """
    Executes Agent 1 (Intake Agent).
    Attempts LLM first; if unavailable, uses deterministic fallback.
    Returns: (IncidentRecord, model_used, error_message)
    """
    prompt = INTAKE_SCHEMA_PROMPT.format(report=report)
    parsed_record, model_used, error_msg = call_llm_json(
        prompt=prompt,
        schema_cls=IncidentRecord,
        system_prompt=SYSTEM_PROMPT
    )

    fallback = deterministic_intake_fallback(report)
    if parsed_record:
        if parsed_record.affected_people is None:
            parsed_record.affected_people = fallback.affected_people
        explicit_threats = [
            h for h in fallback.hazards
            if h.startswith("Reported life threat:") or h == "Reported people trapped"
        ]
        parsed_record.hazards = list(dict.fromkeys(parsed_record.hazards + explicit_threats))
        if fallback.location == "Unknown / Unspecified" or parsed_record.location == "Unknown / Unspecified":
            parsed_record.missing_information.append("Precise address or GPS coordinates missing")
        parsed_record.missing_information = list(dict.fromkeys(parsed_record.missing_information + [LOCATION_WARNING]))
        logger.info(f"Intake agent succeeded using {model_used}")
        return parsed_record, model_used, None

    logger.info("Intake agent executed deterministic fallback")
    return fallback, "deterministic-intake-engine", error_msg
