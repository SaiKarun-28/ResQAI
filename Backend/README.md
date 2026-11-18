# ResQAI – Autonomous Emergency Intelligence & Response Coordination

> **Disclaimer:** ResQAI is an experimental AI decision-support prototype built for hackathon demonstration. It is **NOT** a real emergency dispatch system and cannot dispatch live emergency responders.

## Overview

ResQAI converts raw, unstructured emergency reports into verified, structured incident intelligence records, provisional priority ratings, grounded emergency resource recommendations, and audited action plans through a sequential five-agent architecture.

---

## 5-Agent Architecture

```
Emergency Report (Text)
         │
         ▼
┌──────────────────┐
│   Intake Agent   │ ➔ Extracts category, location, casualties, injuries, missing facts
└────────┬─────────┘
         ▼
┌──────────────────┐
│   Triage Agent   │ ➔ Evaluates urgency indicators & assigns provisional priority
└────────┬─────────┘
         ▼
┌──────────────────┐
│  Resource Agent  │ ➔ Matches grounded facilities from predefined synthetic dataset
└────────┬─────────┘
         ▼
┌──────────────────┐
│  Planning Agent  │ ➔ Generates action plan (safety guidance vs professional action)
└────────┬─────────┘
         ▼
┌──────────────────┐
│Verification Agent│ ➔ Audits grounded resources, flags claims, mandates human review
└────────┬─────────┘
         ▼
Structured JSON Response
```

### Agent Responsibilities
1. **Intake Agent (`app/agents/intake.py`)**:
   - Parses unstructured distress reports into structured `IncidentRecord`.
   - Extracts category (Flood, Fire, Medical, Hazmat, etc.), location, affected people count, reported injuries, and active hazards.
   - Strictly refuses to invent missing details, marking them as `missing_information`.
2. **Triage Agent (`app/agents/triage.py`)**:
   - Evaluates urgency indicators and assigns provisional priority: `Critical`, `High`, `Medium`, or `Low`.
   - Explains reasoning and flags uncertainty caveats.
   - Appends mandatory disclaimer clarifying this is not an official dispatch classification.
3. **Resource Agent (`app/agents/resource.py`)**:
   - Searches predefined synthetic demonstration dataset (`resources.json`).
   - Grounds selections based on category relevance and location matching.
   - Strictly never hallucinates facilities, capacity, or contact details.
4. **Planning Agent (`app/agents/planning.py`)**:
   - Formulates ordered response actions.
   - Explicitly segregates `safety_guidance` (public advisories) from `professional_judgment_action` (responder actions).
   - Associates grounded `resource_id`s with corresponding actions.
5. **Verification Agent (`app/agents/verification.py`)**:
   - Audits all references to ensure resource IDs exist in ground truth.
   - Flags missing evidence, unsupported claims, and contradictions.
   - Enforces human oversight by setting `status: "human_review_required"`.

---

## Technology Stack

- **Python 3.11+**
- **FastAPI** for high-performance REST APIs
- **Pydantic v2** for rigid schema validation and integrity
- **Google Gemini API** (preferred) / **Groq API**
- **Deterministic Fallback Engine** ensuring 100% operational uptime without API keys
- **Uvicorn** ASGI server

---

## API Endpoints & Contract

Base URL: `http://localhost:8000`

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/incidents` | Process emergency report through 5-agent pipeline |
| `GET` | `/api/incidents` | List all processed incidents in current session |
| `GET` | `/api/incidents/{incident_id}` | Retrieve incident details |
| `GET` | `/api/incidents/{incident_id}/trace` | View agent execution trace and metrics |
| `POST` | `/api/incidents/{incident_id}/review` | Record human operator approval/rejection |
| `GET` | `/api/health` | Backend health, provider status & resource count |
| `GET` | `/docs` | Interactive Swagger UI API documentation |

### Sample POST `/api/incidents` Request
```json
{
  "report": "Flood near school. Two people injured."
}
```

### Sample Response
```json
{
  "incident_id": "INC-001",
  "category": "Flood",
  "priority": "Critical",
  "location": "Near school",
  "affected_people": 2,
  "injuries_reported": true,
  "missing_information": [
    "Precise address or GPS coordinates missing",
    "Specific severity and nature of reported injuries unspecified"
  ],
  "agents": {
    "intake": "completed",
    "triage": "completed",
    "resource": "completed",
    "planning": "completed",
    "verification": "completed"
  },
  "resources": [
    {
      "resource_id": "RES-HOSP-003",
      "name": "St. Jude Children's Urgent Care",
      "resource_type": "Hospital",
      "location": "North District, 88 Schoolhouse Lane",
      "availability_status": "Available - 10 Pediatric beds"
    },
    {
      "resource_id": "RES-BOAT-001",
      "name": "Rapid Waters Swiftwater Rescue Taskforce",
      "resource_type": "Water Rescue",
      "location": "Riverside District, Pier 12 Boat Basin",
      "availability_status": "Available - 4 Rescue Boats, 8 Swiftwater Technicians"
    }
  ],
  "action_plan": [
    {
      "step": 1,
      "action": "Advise individuals near the flood zone to seek higher elevation immediately and strictly avoid walking or driving through moving water.",
      "action_type": "safety_guidance",
      "rationale": "Moving floodwaters present immediate risk of drowning; rapid vertical evacuation preserves life prior to team arrival.",
      "assigned_resource_id": null,
      "target": "Public / Affected Individuals"
    },
    {
      "step": 2,
      "action": "Recommend deployment of motorized swiftwater extraction units from Rapid Waters Swiftwater Rescue Taskforce to secure and extract trapped individuals.",
      "action_type": "professional_judgment_action",
      "rationale": "Specialized watercraft and swiftwater technicians are required to safely negotiate moving water obstacles.",
      "assigned_resource_id": "RES-BOAT-001",
      "target": "Rescue Operations Command"
    }
  ],
  "verification": {
    "status": "human_review_required",
    "human_review_required": true,
    "flags": [
      "LOCATION_UNVERIFIED: Responders cannot be routed without manual address verification",
      "DECISION_SUPPORT_SAFEGUARD: Automated dispatch disabled; human operator verification mandatory"
    ],
    "unsupported_claims": [],
    "missing_evidence": [],
    "contradictions": [],
    "verified_resource_ids": [
      "RES-HOSP-003",
      "RES-BOAT-001"
    ]
  }
}
```

---

## Quickstart

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Configure Environment (Optional)
Copy `.env.example` to `.env` and insert your Gemini API Key or Groq API Key:
```bash
cp .env.example .env
```
*Note: If no API key is configured, ResQAI's deterministic fallback engine activates automatically, providing instant, predictable test execution.*

### 3. Start the Server
```bash
uvicorn app.main:app --reload --port 8000
```
Open [http://localhost:8000/docs](http://localhost:8000/docs) to test endpoints interactively.
