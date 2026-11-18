import json
import logging
from copy import deepcopy
from threading import Lock
from pydantic import ValidationError
from typing import List, Dict, Any, Optional
from app.config import RESOURCES_FILE_PATH
from app.schemas.models import ResourceItem

logger = logging.getLogger("resqai.tools.resource_search")

_RESOURCES_CACHE: Optional[List[Dict[str, Any]]] = None
_RESOURCES_LOCK = Lock()


class ResourceDatasetError(RuntimeError):
    """The local synthetic resource dataset could not be loaded or validated."""


def load_resources() -> List[Dict[str, Any]]:
    """Cache only validated data; return isolated copies and retry failed loads."""
    global _RESOURCES_CACHE
    with _RESOURCES_LOCK:
        if _RESOURCES_CACHE is None:
            try:
                with open(RESOURCES_FILE_PATH, "r", encoding="utf-8") as f:
                    raw_resources = json.load(f)
                if not isinstance(raw_resources, list) or not raw_resources:
                    raise ValueError("Expected a nonempty resource list")
                validated = []
                seen_ids = set()
                for raw_resource in raw_resources:
                    resource = ResourceItem.model_validate(raw_resource)
                    if not resource.resource_id.strip() or resource.resource_id in seen_ids:
                        raise ValueError("Resource IDs must be nonempty and unique")
                    seen_ids.add(resource.resource_id)
                    validated.append(resource.model_dump())
                _RESOURCES_CACHE = validated
                logger.info("Loaded %s synthetic resources.", len(validated))
            except (OSError, ValueError, ValidationError) as exc:
                logger.exception("Failed to load or validate synthetic resource dataset")
                raise ResourceDatasetError(
                    "Synthetic resource dataset is unavailable or invalid."
                ) from exc
        return deepcopy(_RESOURCES_CACHE)

def get_resource_by_id(resource_id: str) -> Optional[Dict[str, Any]]:
    """Retrieves a single resource by its unique identifier."""
    resources = load_resources()
    for res in resources:
        if res.get("resource_id") == resource_id:
            return res
    return None

def search_resources(
    category: str,
    location_text: str = "",
    injuries_reported: bool = False,
    hazards: Optional[List[str]] = None,
    max_results: int = 5
) -> List[ResourceItem]:
    """
    Deterministically searches predefined JSON resource dataset.
    Never fabricates facilities, availability, capacity, or contact details.
    """
    resources = load_resources()
    if not resources:
        return []

    matched: List[ResourceItem] = []
    cat_lower = (category or "").lower()
    loc_lower = (location_text or "").lower()
    hazards_lower = [h.lower() for h in (hazards or [])]

    # Map categories to relevant resource types
    category_relevance_map = {
        "flood": ["Water Rescue", "Shelter", "Hospital", "Logistics & Power"],
        "fire": ["Fire & Rescue", "Hospital", "Mobile Medical", "Shelter", "Hazmat"],
        "medical": ["Hospital", "Mobile Medical"],
        "hazmat": ["Hazmat", "Hospital", "Mobile Medical", "Shelter"],
        "earthquake": ["Search & Rescue", "Hospital", "Shelter", "Mobile Medical", "Logistics & Power"],
        "traffic accident": ["Hospital", "Fire & Rescue", "Mobile Medical"],
        "storm": ["Shelter", "Logistics & Power", "Water Rescue", "Hospital"],
        "building collapse": ["Search & Rescue", "Hospital", "Mobile Medical", "Fire & Rescue"]
    }

    relevant_types = []
    for k, v in category_relevance_map.items():
        if k in cat_lower:
            relevant_types.extend(v)

    if injuries_reported and "Hospital" not in relevant_types:
        relevant_types.insert(0, "Hospital")
    if injuries_reported and "Mobile Medical" not in relevant_types:
        relevant_types.append("Mobile Medical")

    # If no specific category matched, provide general emergency types
    if not relevant_types:
        relevant_types = ["Hospital", "Fire & Rescue", "Shelter", "Mobile Medical"]

    # Scoring candidates
    scored_candidates = []
    for res in resources:
        score = 0.0
        evidence: List[str] = []
        r_type = res.get("resource_type", "")
        r_loc = res.get("location", "").lower()
        r_desc = res.get("description", "").lower()
        r_name = res.get("name", "").lower()

        # Type relevance
        if r_type in relevant_types:
            rank = relevant_types.index(r_type)
            type_score = max(5.0 - rank, 1.0)
            score += type_score
            evidence.append(f"Resource type '{r_type}' aligns with incident category '{category}'")

        # Injury-driven relevance
        if injuries_reported and r_type in ["Hospital", "Mobile Medical"]:
            score += 3.0
            evidence.append("Matched for reported medical casualties and triage need")

        # Location text matching
        loc_tokens = [tok.strip(",.") for tok in loc_lower.split() if len(tok) > 3]
        for token in loc_tokens:
            if token in r_loc or token in r_name or token in r_desc:
                score += 2.5
                evidence.append(f"Location match on keyword '{token}'")

        # Hazard matching
        for hazard in hazards_lower:
            if any(h_word in r_desc or h_word in r_name for h_word in hazard.split() if len(h_word) > 3):
                score += 2.0
                evidence.append(f"Capability matches hazard '{hazard}'")

        if score > 0:
            match_reason = f"Selected based on {', '.join(evidence[:2])}."
            item = ResourceItem(
                resource_id=res["resource_id"],
                name=res["name"],
                resource_type=res["resource_type"],
                location=res["location"],
                description=res["description"],
                source=res["source"],
                last_updated=res["last_updated"],
                availability_status=res["availability_status"],
                match_reason=match_reason,
                evidence=evidence
            )
            scored_candidates.append((score, item))

    # Sort descending by score
    scored_candidates.sort(key=lambda x: x[0], reverse=True)

    # Return top max_results
    return [c[1] for c in scored_candidates[:max_results]]
