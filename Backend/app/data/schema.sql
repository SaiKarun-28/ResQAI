-- ResQAI 2.0 SQLite Schema
-- Sequences table for incident IDs
CREATE TABLE IF NOT EXISTS incident_sequence (
    id INTEGER PRIMARY KEY
);
INSERT OR IGNORE INTO incident_sequence (id) VALUES (0);

-- Incident table
CREATE TABLE IF NOT EXISTS incidents (
    incident_id TEXT PRIMARY KEY,
    category TEXT,
    priority TEXT,
    location TEXT,
    location_lat REAL,
    location_lon REAL,
    location_accuracy REAL,
    location_source TEXT,
    location_timestamp TEXT,
    affected_people INTEGER,
    injuries_reported BOOLEAN,
    missing_information TEXT,
    raw_report TEXT,
    transcript_confidence REAL,
    agents_status TEXT,
    resources TEXT,
    action_plan TEXT,
    verification TEXT,
    hazard_assessment TEXT,
    rescue_plan TEXT,
    trace TEXT,
    human_review TEXT,
    created_at TEXT,
    updated_at TEXT,
    invalidated_at TEXT
);

-- Dispatch request table
CREATE TABLE IF NOT EXISTS dispatch_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    incident_id TEXT,
    plan_id TEXT,
    resource_category TEXT,
    quantity INTEGER,
    status TEXT,
    rationale TEXT,
    is_simulated BOOLEAN,
    created_at TEXT,
    updated_at TEXT,
    FOREIGN KEY (incident_id) REFERENCES incidents (incident_id)
);

-- Audit events table
CREATE TABLE IF NOT EXISTS audit_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    incident_id TEXT,
    actor TEXT,
    action TEXT,
    details TEXT,
    timestamp TEXT,
    FOREIGN KEY (incident_id) REFERENCES incidents (incident_id)
);