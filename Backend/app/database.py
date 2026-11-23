"""SQLite persistence layer for ResQAI."""

import sqlite3
import json
import logging
import re
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Optional, List, Dict
from datetime import datetime, timezone
from threading import Lock

from app.config import BASE_DIR

logger = logging.getLogger("resqai.database")

DB_PATH = BASE_DIR / "data" / "resqai.db"
SCHEMA_PATH = BASE_DIR / "data" / "schema.sql"

# Thread-safe connection pool (simple single-connection for SQLite)
_DB_LOCK = Lock()
_conn: Optional[sqlite3.Connection] = None


def get_connection() -> sqlite3.Connection:
    """Get or create the SQLite connection."""
    global _conn
    with _DB_LOCK:
        if _conn is None:
            DB_PATH.parent.mkdir(parents=True, exist_ok=True)
            _conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
            _conn.row_factory = sqlite3.Row
            _conn.execute("PRAGMA foreign_keys = ON")
            _conn.execute("PRAGMA journal_mode = WAL")
            _reconcile_schema(_conn)
            logger.info("SQLite database opened at %s", DB_PATH)
        return _conn


def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    """Check if a table exists in the database."""
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,)
    )
    return cursor.fetchone() is not None


def initialize_database() -> None:
    """Create tables from schema file if they don't exist, then reconcile columns."""
    conn = get_connection()
    if SCHEMA_PATH.exists():
        with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
            schema_sql = f.read()
        conn.executescript(schema_sql)
        logger.info("Database schema initialized from %s", SCHEMA_PATH)
        _reconcile_schema(conn)
    else:
        logger.warning("Schema file not found at %s", SCHEMA_PATH)


_SQL_TYPES = {"TEXT", "INTEGER", "REAL", "BOOLEAN", "BLOB", "NUMERIC"}


def _reconcile_schema(conn: sqlite3.Connection) -> None:
    """Add any columns schema.sql declares but an existing table lacks.

    'CREATE TABLE IF NOT EXISTS' never alters an existing table, so a DB created
    before a column was added stays out of sync with schema.sql. This walks every
    table definition in schema.sql and ALTERs in whatever is missing. New tables
    (e.g. future phases) need no special-casing.
    """
    if not SCHEMA_PATH.exists():
        return
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        schema_sql = f.read()
    for table_match in re.finditer(r"CREATE TABLE IF NOT EXISTS (\w+)\s*\((.*?)\)\s*;", schema_sql, re.S):
        table_name = table_match.group(1)
        if not _table_exists(conn, table_name):
            continue
        # Line-based parse: a column line starts with a name and a known SQL type;
        # skip constraint lines (PRIMARY KEY, FOREIGN KEY, UNIQUE, CHECK ...).
        declared = {}
        for line in table_match.group(2).splitlines():
            parts = line.strip().rstrip(",").split()
            if len(parts) >= 2 and parts[0].isidentifier() and parts[1].upper() in _SQL_TYPES:
                declared[parts[0]] = " ".join(parts[1:])
        existing = {
            row["name"]
            for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()
        }
        for name, col_type in declared.items():
            if name not in existing:
                conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {name} {col_type}")
                logger.info("Added missing column: %s.%s %s", table_name, name, col_type)
    conn.commit()


def wipe_database() -> None:
    """Wipe the database file for testing."""
    global _conn
    with _DB_LOCK:
        if _conn:
            _conn.close()
            _conn = None
        if DB_PATH.exists():
            DB_PATH.unlink()
            logger.info("Database wiped.")


def execute_query(sql: str, params: tuple = ()) -> List[sqlite3.Row]:
    """Execute a SELECT query and return rows."""
    conn = get_connection()
    cursor = conn.execute(sql, params)
    return cursor.fetchall()


def execute_write(sql: str, params: tuple = ()) -> int:
    """Execute an INSERT/UPDATE/DELETE and return last rowid."""
    conn = get_connection()
    cursor = conn.execute(sql, params)
    conn.commit()
    return cursor.lastrowid


@contextmanager
def transaction():
    """Context manager for database transactions."""
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise


# --- Incident operations ---

def create_incident(
    incident_id: str,
    category: str,
    priority: str,
    location: str,
    location_lat: Optional[float],
    location_lon: Optional[float],
    location_accuracy: Optional[float],
    location_source: Optional[str],
    location_timestamp: Optional[str],
    affected_people: Optional[int],
    injuries_reported: bool,
    missing_information: List[str],
    raw_report: str,
    agents_status: Dict[str, str],
    resources: List[Dict],
    action_plan: List[Dict],
    verification: Dict,
    hazard_assessment: Optional[Dict] = None,
    rescue_plan: Optional[Dict] = None,
    trace: Optional[List[Dict]] = None,
    human_review: Optional[Dict] = None,
) -> None:
    """Insert a new incident record."""
    now = datetime.now(timezone.utc).isoformat()
    with transaction() as conn:
        conn.execute(
            """
            INSERT INTO incidents (
                incident_id, category, priority, location, location_lat, location_lon,
                location_accuracy, location_source, location_timestamp,
                affected_people, injuries_reported, missing_information,
                raw_report, transcript_confidence, agents_status, resources, action_plan, verification,
                hazard_assessment, rescue_plan, trace, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                incident_id, category, priority, location, location_lat, location_lon,
                location_accuracy, location_source, location_timestamp,
                affected_people, injuries_reported, json.dumps(missing_information),
                raw_report, None, json.dumps(agents_status), json.dumps(resources),
                json.dumps(action_plan), json.dumps(verification),
                json.dumps(hazard_assessment) if hazard_assessment else None,
                json.dumps(rescue_plan) if rescue_plan else None,
                json.dumps(trace) if trace else None,
                now, now,
            ),
        )


def get_incident(incident_id: str) -> Optional[Dict]:
    """Retrieve an incident by ID."""
    rows = execute_query(
        "SELECT * FROM incidents WHERE incident_id = ?", (incident_id,)
    )
    if not rows:
        return None
    row = rows[0]
    return _row_to_incident(row)


def list_incidents() -> List[Dict]:
    """List all incidents ordered by creation time descending."""
    rows = execute_query("SELECT * FROM incidents ORDER BY created_at DESC")
    return [_row_to_incident(row) for row in rows]


def update_incident_location(
    incident_id: str,
    lat: float,
    lon: float,
    accuracy: Optional[float],
    source: str,
    timestamp: str,
) -> bool:
    """Update incident location fields."""
    now = datetime.now(timezone.utc).isoformat()
    with transaction() as conn:
        cursor = conn.execute(
            """
            UPDATE incidents SET
                location_lat = ?, location_lon = ?, location_accuracy = ?,
                location_source = ?, location_timestamp = ?,
                updated_at = ?
            WHERE incident_id = ?
            """,
            (lat, lon, accuracy, source, timestamp, now, incident_id),
        )
        return cursor.rowcount > 0


def update_incident_transcript(incident_id: str, transcript: str, confidence: Optional[float]) -> bool:
    """Update incident with voice transcript."""
    now = datetime.now(timezone.utc).isoformat()
    with transaction() as conn:
        cursor = conn.execute(
            "UPDATE incidents SET raw_report = ?, transcript_confidence = ?, updated_at = ? WHERE incident_id = ?",
            (transcript, confidence, now, incident_id),
        )
        return cursor.rowcount > 0


def update_incident_hazard_assessment(incident_id: str, hazard_assessment: Dict) -> bool:
    """Update hazard assessment for an incident."""
    now = datetime.now(timezone.utc).isoformat()
    with transaction() as conn:
        cursor = conn.execute(
            "UPDATE incidents SET hazard_assessment = ?, updated_at = ? WHERE incident_id = ?",
            (json.dumps(hazard_assessment), now, incident_id),
        )
        return cursor.rowcount > 0


def update_incident_rescue_plan(incident_id: str, rescue_plan: Dict, version: int) -> bool:
    """Update rescue plan for an incident."""
    now = datetime.now(timezone.utc).isoformat()
    with transaction() as conn:
        cursor = conn.execute(
            "UPDATE incidents SET rescue_plan = ?, updated_at = ? WHERE incident_id = ?",
            (json.dumps(rescue_plan), now, incident_id),
        )
        return cursor.rowcount > 0


def update_incident_approval(incident_id: str, plan_version: int, approval_data: Dict) -> bool:
    """Record human review/approval."""
    with transaction() as conn:
        cursor = conn.execute(
            "UPDATE incidents SET human_review = ?, updated_at = ? WHERE incident_id = ?",
            (json.dumps(approval_data), datetime.now(timezone.utc).isoformat(), incident_id),
        )
        return cursor.rowcount > 0


def invalidate_incident_approval(incident_id: str) -> bool:
    """Invalidate existing approval (set human_review.reviewed = false)."""
    with transaction() as conn:
        # Get current review
        rows = execute_query("SELECT human_review FROM incidents WHERE incident_id = ?", (incident_id,))
        if not rows:
            return False
        current = json.loads(rows[0]["human_review"] or "{}")
        current["reviewed"] = False
        current["invalidated_at"] = datetime.now(timezone.utc).isoformat()
        cursor = conn.execute(
            "UPDATE incidents SET human_review = ?, updated_at = ? WHERE incident_id = ?",
            (json.dumps(current), datetime.now(timezone.utc).isoformat(), incident_id),
        )
        return cursor.rowcount > 0


# --- Dispatch request operations ---

def create_dispatch_request(
    incident_id: str,
    plan_id: str,
    resource_category: str,
    quantity: int,
    rationale: str,
) -> int:
    """Create a simulated dispatch request."""
    now = datetime.now(timezone.utc).isoformat()
    with transaction() as conn:
        cursor = conn.execute(
            """
            INSERT INTO dispatch_requests (
                incident_id, plan_id, resource_category, quantity,
                status, rationale, is_simulated, created_at, updated_at
            ) VALUES (?, ?, ?, ?, 'created_simulated', ?, 1, ?, ?)
            """,
            (incident_id, plan_id, resource_category, quantity, rationale, now, now),
        )
        return cursor.lastrowid


def get_dispatch_requests(incident_id: str) -> List[Dict]:
    """Get all dispatch requests for an incident."""
    rows = execute_query(
        "SELECT * FROM dispatch_requests WHERE incident_id = ? ORDER BY created_at", (incident_id,)
    )
    return [_row_to_dispatch_request(row) for row in rows]


def update_dispatch_request_status(request_id: int, status: str) -> bool:
    """Update dispatch request status."""
    now = datetime.now(timezone.utc).isoformat()
    with transaction() as conn:
        cursor = conn.execute(
            "UPDATE dispatch_requests SET status = ?, updated_at = ? WHERE id = ?",
            (status, now, request_id),
        )
        return cursor.rowcount > 0


# --- Audit event operations ---

def record_audit_event(incident_id: str, actor: str, action: str, details: Dict) -> None:
    """Record an audit event."""
    now = datetime.now(timezone.utc).isoformat()
    with transaction() as conn:
        conn.execute(
            """
            INSERT INTO audit_events (incident_id, actor, action, details, timestamp)
            VALUES (?, ?, ?, ?, ?)
            """,
            (incident_id, actor, action, json.dumps(details), now),
        )


def get_audit_events(incident_id: str) -> List[Dict]:
    """Get audit events for an incident."""
    rows = execute_query(
        "SELECT * FROM audit_events WHERE incident_id = ? ORDER BY timestamp", (incident_id,)
    )
    return [dict(row) for row in rows]


# --- Helper functions ---

def _row_to_incident(row: sqlite3.Row) -> Dict:
    """Convert a database row to incident dict."""
    data = dict(row)
    # Parse JSON fields
    for field in ("missing_information", "agents_status", "resources", "action_plan", "verification", "hazard_assessment", "rescue_plan", "trace", "human_review"):
        if data.get(field):
            try:
                data[field] = json.loads(data[field])
            except json.JSONDecodeError:
                data[field] = None
        else:
            data[field] = None if field != "missing_information" else []

    # Map agents_status -> agents for API contract compatibility
    if data.get("agents_status"):
        data["agents"] = data.pop("agents_status")
    return data


def _row_to_dispatch_request(row: sqlite3.Row) -> Dict:
    """Convert a database row to dispatch request dict."""
    data = dict(row)
    return data