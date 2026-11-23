import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from app.database import get_connection, SCHEMA_PATH, _reconcile_schema, create_incident

conn = get_connection()
_reconcile_schema(conn)
cols = {r["name"] for r in conn.execute("PRAGMA table_info(incidents)")}
print("transcript_confidence present:", "transcript_confidence" in cols)
print("cols:", sorted(cols))