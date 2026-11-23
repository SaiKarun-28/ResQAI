"""Geospatial hazard-zone check (Phase 3).

Deterministic point-in-polygon (even-odd ray casting) against a local GeoJSON
hazard-zone dataset. stdlib-only; deliberately no Shapely dependency.
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Tuple

from app.config import BASE_DIR
from app.schemas.models import IncidentRecord, HazardAssessment

logger = logging.getLogger("resqai.agents.geospatial")

HAZARD_ZONES_PATH = BASE_DIR / "data" / "hazard_zones.geojson"


def _point_in_polygon(lat: float, lon: float, ring) -> bool:
    """Even-odd ray casting; True if (lon, lat) is inside the closed ring."""
    inside = False
    j = len(ring) - 1
    for i in range(len(ring)):
        xi, yi = ring[i]
        xj, yj = ring[j]
        # ring coords are [lon, lat]
        if ((yi > lat) != (yj > lat)) and (
            lon < (xj - xi) * (lat - yi) / (yj - yi) + xi
        ):
            inside = not inside
        j = i
    return inside


def _point_in_polygon_multi(lat: float, lon: float, polygon) -> bool:
    """Polygon is [outer, *holes]; inside = in outer and in no hole."""
    outer = polygon[0]
    if not _point_in_polygon(lat, lon, outer):
        return False
    return not any(_point_in_polygon(lat, lon, hole) for hole in polygon[1:])


def _load_zones() -> List[dict]:
    """Return the list of hazard-zone features; empty if dataset missing/bad."""
    if not HAZARD_ZONES_PATH.exists():
        logger.warning("Hazard zone dataset missing at %s", HAZARD_ZONES_PATH)
        return []
    try:
        with open(HAZARD_ZONES_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("Could not load hazard zone dataset: %s", e)
        return []
    return data.get("features", [])


def run_geospatial_agent(record: IncidentRecord) -> Tuple[HazardAssessment, str, Optional[str]]:
    """Check incident coords against local hazard zones.

    The incident's coordinates are not populated at orchestration time (browser
    GPS arrives after incident creation), so without coords this returns an
    honest 'unknown' assessment. Call run_geospatial_assessment directly when
    coords are known (e.g. after a location update).
    """
    return run_geospatial_assessment(
        location_lat=None,
        location_lon=None,
        hazard_type_hint=next(iter(record.hazards), None),
    ), "deterministic-geospatial-checker", None


def run_geospatial_assessment(
    location_lat: Optional[float],
    location_lon: Optional[float],
    hazard_type_hint: Optional[str] = None,
) -> HazardAssessment:
    """Run the point-in-polygon check against known coordinates."""
    today = datetime.now(timezone.utc).date().isoformat()
    if location_lat is None or location_lon is None:
        return HazardAssessment(
            status="unknown_due_to_coverage_or_missing_data",
            source="ResQAI Synthetic Hazard Zones (local GeoJSON)",
            date=today,
            coverage="No coordinates provided; location must be captured before hazard assessment",
        )

    zones = _load_zones()
    if not zones:
        return HazardAssessment(
            status="unknown_due_to_coverage_or_missing_data",
            source="ResQAI Synthetic Hazard Zones (local GeoJSON)",
            date=today,
            coverage="Hazard zone dataset unavailable",
            location_lat=location_lat,
            location_lon=location_lon,
        )

    for feature in zones:
        geometry = feature.get("geometry", {})
        props = feature.get("properties", {})
        if geometry.get("type") == "Polygon":
            hits = _point_in_polygon_multi(location_lat, location_lon, geometry["coordinates"])
        elif geometry.get("type") == "MultiPolygon":
            hits = any(
                _point_in_polygon_multi(location_lat, location_lon, poly)
                for poly in geometry["coordinates"]
            )
        else:
            hits = False
        if hits:
            return HazardAssessment(
                status="inside_known_hazard_zone",
                source="ResQAI Synthetic Hazard Zones (local GeoJSON)",
                date=today,
                coverage=props.get("coverage"),
                hazard_type=props.get("hazard_type"),
                inside_polygon=True,
                location_lat=location_lat,
                location_lon=location_lon,
                polygon_id=props.get("id"),
            )

    return HazardAssessment(
        status="outside_known_zone",
        source="ResQAI Synthetic Hazard Zones (local GeoJSON)",
        date=today,
        coverage="No matching synthetic hazard zone for coordinates",
        inside_polygon=False,
        location_lat=location_lat,
        location_lon=location_lon,
    )


if __name__ == "__main__":
    # Self-check: a point inside HZ-FLOOD-001 must be flagged.
    check = run_geospatial_assessment(19.04, 72.85)
    assert check.status == "inside_known_hazard_zone", check.status
    assert check.polygon_id == "HZ-FLOOD-001", check.polygon_id
    outside = run_geospatial_assessment(28.0, 77.0)
    assert outside.status == "outside_known_zone", outside.status
    missing = run_geospatial_assessment(None, None)
    assert missing.status == "unknown_due_to_coverage_or_missing_data", missing.status
    print("geospatial self-check OK")