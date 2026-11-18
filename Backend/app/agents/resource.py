import logging
from typing import List, Tuple, Optional
from app.schemas.models import IncidentRecord, TriageRecord, ResourceItem
from app.tools.resource_search import search_resources, load_resources

logger = logging.getLogger("resqai.agents.resource")

def run_resource_agent(
    record: IncidentRecord,
    triage: TriageRecord
) -> Tuple[List[ResourceItem], str, Optional[str]]:
    """
    Executes Agent 3 (Resource Agent).
    Searches the predefined synthetic JSON dataset.
    Strictly guarantees NEVER fabricating facilities, availability, capacity, or contact details.
    All returned items come directly from the predefined dataset.
    """
    try:
        matched_resources = search_resources(
            category=record.category,
            location_text=record.location,
            injuries_reported=record.injuries_reported,
            hazards=record.hazards,
            max_results=5
        )

        # Verification step to ensure no hallucination
        available_dataset = {r["resource_id"]: r for r in load_resources()}
        validated_items: List[ResourceItem] = []

        for item in matched_resources:
            if item.resource_id in available_dataset:
                db_record = available_dataset[item.resource_id]
                # Enforce authentic data integrity
                item.name = db_record["name"]
                item.resource_type = db_record["resource_type"]
                item.location = db_record["location"]
                item.description = db_record["description"]
                item.source = db_record["source"]
                item.last_updated = db_record["last_updated"]
                item.availability_status = db_record["availability_status"]
                validated_items.append(item)
            else:
                logger.warning(f"Discarding fabricated or unmatched resource ID: {item.resource_id}")

        logger.info(f"Resource agent successfully retrieved {len(validated_items)} grounded resources")
        return validated_items, "grounded-resource-retriever", None

    except Exception as e:
        err_msg = f"Resource agent execution failed: {str(e)}"
        logger.error(err_msg)
        return [], "grounded-resource-retriever", err_msg
