# ResQAI – Autonomous Emergency Intelligence & Response Coordination
## Complete Project Implementation, Architecture & Engineering Report

> **Decision-Support Prototype Disclaimer:** ResQAI is an experimental AI decision-support prototype built for hackathon demonstration. It is **NOT** a real emergency dispatch system and cannot dispatch live emergency responders. Automated dispatch is disabled by architectural design.

---

## 1. Executive Summary & Project Objective

**ResQAI** was built to address a critical bottleneck in disaster response: converting unstructured, noisy, and high-stress citizen emergency reports into structured, actionable, and verified incident records. 

The primary objective was to build a functional **multi-agent AI backend** that:
1. Ingests raw unstructured text reports (e.g., *"Flood near school. Two people injured."*).
2. Extracts structured incident data without fabricating missing details.
3. Performs provisional emergency triage and urgency assessment.
4. Retrieves grounded emergency resources from a predefined synthetic demonstration dataset.
5. Formulates an ordered response plan clearly distinguishing public safety guidance from professional responder actions.
6. Rigorously audits the output for hallucinated facilities or contradictory claims, enforcing human-in-the-loop review.
7. Exposes an exact API contract over FastAPI with live session history, execution tracing, and human review recording.

---

## 2. Technology Stack & Design Decisions

To maximize performance, reliability, and hackathon evaluation criteria while avoiding fragile abstractions, the following stack was used:

- **Python 3.11+**: Core runtime environment.
- **FastAPI**: High-throughput asynchronous REST API framework with native OpenAPI (`/docs`) generation.
- **Pydantic v2**: Strict schema validation for all agent inputs, outputs, and API responses.
- **Google Gemini API (`google-genai` SDK)**: Modern official Gemini SDK utilizing `gemini-3.5-flash-lite` with model failover (`gemini-3.8-flash`).
- **Uvicorn**: Production-grade ASGI server with hot-reload and CORS middleware enabled for React/Vite development servers.
- **Predefined JSON Storage (`resources.json`)**: Deterministic, verifiable ground-truth resource dataset with zero hallucinated facilities.
- **Zero Heavy Frameworks**: No LangChain, no vector databases, no Docker, no PostgreSQL, and no external workflow managers (n8n), ensuring instant setup, low latency, and zero dependency friction.

---

## 3. Five-Agent Architecture & Data Flow

The system coordinates five specialized agents sequentially through a central Python orchestrator:

```
                      Emergency Distress Report (Raw Text)
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 1. INTAKE AGENT (app/agents/intake.py)                                       │
│    • Analyzes report text                                                   │
│    • Extracts category (Flood, Fire, Medical, Hazmat, etc.)                 │
│    • Identifies location landmark and counts affected individuals           │
│    • Extracts reported injuries and active environmental hazards            │
│    • Flags missing information (NEVER invents details)                      │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │ Structured IncidentRecord
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 2. TRIAGE AGENT (app/agents/triage.py)                                       │
│    • Evaluates urgency indicators & life-safety threats                      │
│    • Assigns provisional priority: Critical, High, Medium, or Low           │
│    • Formulates detailed reasoning justification                            │
│    • Flags uncertainty caveats and gaps                                     │
│    • Attaches non-official classification legal disclaimer                  │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │ TriageRecord
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 3. RESOURCE AGENT (app/agents/resource.py)                                   │
│    • Queries predefined synthetic dataset (resources.json)                  │
│    • Matches facilities based on incident category and location proximity   │
│    • Generates evidence-backed selection reasoning                          │
│    • STRICT GROUNDING: Never hallucinates facilities or capacities          │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │ List[ResourceItem] (Grounded)
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 4. PLANNING AGENT (app/agents/planning.py)                                   │
│    • Formulates sequential response action steps                            │
│    • SEPARATES 'safety_guidance' (public advice) from                      │
│      'professional_judgment_action' (trained responder action)              │
│    • Maps grounded resource IDs (e.g. RES-BOAT-001, RES-HOSP-001)           │
│    • Assigns specific target parties (Public, EMS, Incident Commander)      │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │ List[PlanAction]
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 5. VERIFICATION AGENT (app/agents/verification.py)                           │
│    • Audits referenced resource IDs against ground-truth database           │
│    • Flags unsupported claims and missing evidence (e.g. unverified address)│
│    • Checks for contradictions (e.g. injuries reported without medical aid) │
│    • Mandates human oversight (status: "human_review_required")             │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │ VerificationData
                                       ▼
                      Structured JSON Incident Response
```

---

## 4. Complete Inventory of Implemented Files

```
c:\Users\shiva\Desktop\hackathon\
├── app/
│   ├── __init__.py                # Package exports
│   ├── main.py                    # FastAPI application, CORS middleware & lifespan
│   ├── config.py                  # Environment config, API keys & timeout settings
│   ├── api/
│   │   ├── __init__.py            # Router package
│   │   └── routes.py              # REST API endpoints (/api/incidents, /api/health, etc.)
│   ├── agents/
│   │   ├── __init__.py            # 5-Agent exports
│   │   ├── intake.py              # Agent 1: Structured report extraction & gap detection
│   │   ├── triage.py              # Agent 2: Urgency assessment & provisional priority
│   │   ├── resource.py            # Agent 3: Grounded facility retrieval
│   │   ├── planning.py            # Agent 4: Safety guidance vs responder action planning
│   │   └── verification.py        # Agent 5: Hallucination audit & verification flags
│   ├── orchestrator/
│   │   ├── __init__.py            # Orchestrator exports
│   │   └── workflow.py            # Sequential workflow engine & in-memory session store
│   ├── schemas/
│   │   ├── __init__.py            # Schema exports
│   │   └── models.py              # Pydantic v2 data models for API contract & agents
│   ├── tools/
│   │   ├── __init__.py            # Tool exports
│   │   ├── llm_client.py          # Google GenAI client with failover & retry handling
│   │   └── resource_search.py     # Deterministic query engine for synthetic facilities
│   └── data/
│       └── resources.json         # 12 synthetic demonstration facilities
├── tests/
│   ├── test_direct.py             # 9-point end-to-end automated test suite
│   └── test_resqai.py             # Pytest test suite
├── .env                           # Configured environment variables (API Key loaded)
├── .env.example                   # Template environment variables
├── requirements.txt               # Pinned Python package dependencies
├── README.md                      # Quickstart and overview guide
└── PROJECT_OVERVIEW.md            # Comprehensive architecture & engineering report
```

*(Note: The exact structure is mirrored in `resqai-backend/` to ensure seamless execution from either directory).*

---

## 5. What Was Done & How It Was Completed

### Step 1: Package Environment & Dependency Setup
- Installed modern packages: `fastapi`, `pydantic`, `uvicorn`, `python-dotenv`, `google-genai`, `google-generativeai`, and `groq`.
- Verified clean package imports under Python 3.11.4.

### Step 2: Synthetic Demonstration Dataset (`app/data/resources.json`)
- Created 12 fictional, non-operational demonstration records meeting all required fields:
  - `resource_id`: (e.g. `RES-HOSP-001`, `RES-BOAT-001`, `RES-FIRE-001`, `RES-SHEL-001`, `RES-HAZM-001`, `RES-SAR-001`)
  - `name`: Descriptive fictional facility names
  - `resource_type`: Hospital, Shelter, Fire & Rescue, Water Rescue, Hazmat, Mobile Medical, Search & Rescue, Logistics & Power
  - `location`: Fictional municipal districts (Central District, North District, Riverside District)
  - `description`: Capabilities, trauma bays, rescue boats, ICU beds
  - `source`: Explicitly labeled `"ResQAI Synthetic Demonstration Dataset - Fictional (Non-operational)"`
  - `last_updated`: ISO timestamp
  - `availability_status`: Operational readiness status

### Step 3: Pydantic Schema Models & Contract Compliance (`app/schemas/models.py`)
- Modeled the exact JSON contract specified in the prompt:
  - `incident_id`: (e.g., `"INC-001"`)
  - `category`: (e.g., `"Flood"`)
  - `priority`: (e.g., `"Critical"`)
  - `location`: (e.g., `"Near school"`)
  - `affected_people`: Integer casualty count (e.g., `2`)
  - `injuries_reported`: Boolean flag
  - `missing_information`: String array of unconfirmed gaps
  - `agents`: Dictionary of status strings (`intake`, `triage`, `resource`, `planning`, `verification`)
  - `resources`: Array of matched grounded facilities
  - `action_plan`: Ordered response steps separating public safety guidance from professional responder action
  - `verification`: Status (`"human_review_required"`) and auditor flags
- Added non-intrusive supplementary metadata:
  - `trace`: Array of per-agent duration (ms), models used, and execution summaries
  - `human_review`: Approval/rejection record, reviewer ID, timestamp, and legal disclaimer
  - `disclaimer`: Permanent decision-support advisory notice

### Step 4: Google Gemini API Integration (`app/tools/llm_client.py`)
- Integrated the user-provided Gemini API key into `.env`.
- **Model Discovery & Adaptation**:
  - Tested legacy models (`gemini-2.5-flash`, `gemini-1.5-flash`), which returned Google API deprecation notices directing usage to modern models.
  - Successfully queried Google's model catalog and verified that `gemini-3.5-flash-lite` is fully active and responsive.
  - Adapted `llm_client.py` to use `google.genai` SDK with automatic failover between `gemini-3.5-flash-lite`, `gemini-3.8-flash`, and `gemini-3.1-flash-lite`.
  - Configured Google's mandatory minimum deadline requirement (`timeout=15000ms`).
  - Added clean JSON fence extraction and structured Pydantic deserialization with single-retry recovery.

### Step 5: Implementation of the Five Specialized Agents
1. **Intake Agent (`app/agents/intake.py`)**:
   - Analyzes raw report text.
   - Extracts category, location context, casualty counts, and injury indicators.
   - Strictly catalogs gaps in `missing_information` rather than guessing or fabricating details.
   - Implemented a rule-based fallback regex engine that ensures zero downtime if the LLM API is unavailable.
2. **Triage Agent (`app/agents/triage.py`)**:
   - Assesses dynamic hazards and injury severity.
   - Assigns provisional priority: `Critical` (life-safety threat with casualties/rising water/fire), `High` (active hazard or injuries), `Medium` (property/structural check without injuries), `Low` (minor advisory).
   - Generates transparent justification text and highlights uncertainty caveats.
3. **Resource Agent (`app/agents/resource.py` & `app/tools/resource_search.py`)**:
   - Performs grounded querying against `resources.json`.
   - Multi-factor scoring combines incident category relevance, keyword location proximity, and specific injury needs (e.g., prioritizing trauma hospitals when casualties exist).
   - Cross-checks all candidate IDs against the ground-truth dataset to prevent hallucinated resources.
4. **Planning Agent (`app/agents/planning.py`)**:
   - Produces sequential action steps.
   - Crucial separation:
     - `action_type: "safety_guidance"`: Guidance for the public (e.g., seek higher elevation, avoid driving through moving water, stay low under smoke).
     - `action_type: "professional_judgment_action"`: Tactical guidance for trained dispatchers and commanders (e.g., stage motorized swiftwater rescue boats, alert trauma teams).
   - Links retrieved resource IDs (`assigned_resource_id`) directly to relevant action steps.
5. **Verification Agent (`app/agents/verification.py`)**:
   - Checks every resource ID referenced in the action plan against the ground truth dataset.
   - Verifies whether injuries have corresponding medical resources assigned.
   - Flags missing location addresses (`LOCATION_UNVERIFIED`).
   - Mandates human sign-off (`human_review_required: true`).

### Step 6: Sequential Orchestrator (`app/orchestrator/workflow.py`)
- Coordinates: Intake ➔ Triage ➔ Resource ➔ Planning ➔ Verification.
- Measures high-resolution execution time (`duration_ms`) for each agent.
- Captures granular execution state in `trace`.
- Implements thread-safe in-memory session persistence (`incident_store`) to support instant retrieval and human review operations.
- Guarantees that failed agents are never falsely marked as completed.

### Step 7: REST API Endpoints (`app/api/routes.py`)
- `POST /api/incidents`: Executes 5-agent pipeline; returns full incident record.
- `GET /api/incidents`: Lists all incidents processed in the current session.
- `GET /api/incidents/{incident_id}`: Retrieves specific incident record.
- `GET /api/incidents/{incident_id}/trace`: Returns agent timing, model, and status trace.
- `POST /api/incidents/{incident_id}/review`: Records operator review decision (`approve` / `reject`), reviewer notes, and appends the non-dispatch advisory notice.
- `GET /api/health`: Returns system status, loaded resource count, and active provider.
- `GET /docs`: Swagger UI interactive exploration.

### Step 8: Frontend Integration & CORS Configuration (`app/main.py`)
- Configured FastAPI `CORSMiddleware` with `allow_origins=["*"]`, enabling out-of-the-box integration with React, Vite, Next.js, and browser clients on ports 3000, 5173, and 8000.

---

## 6. Testing & Quality Assurance Verification

A dedicated end-to-end verification script ([tests/test_direct.py](file:///c:/Users/shiva/Desktop/hackathon/tests/test_direct.py)) was executed against both the deterministic engine and the live Google Gemini API.

### Test Results Matrix

| # | Test Case Scenario | Expected Behavior | Result |
|---|---|---|:---:|
| **1** | Health Endpoint Check | Status healthy, >=10 resources, active provider reported | **PASS** |
| **2** | Flood Emergency with Injuries | Priority Critical, 2 affected, injuries True, water rescue & hospital matched, plan contains both safety guidance and responder action | **PASS** |
| **3** | Fire Emergency | Priority High/Critical, Fire apparatus & shelter staged | **PASS** |
| **4** | Vague Report (Missing Location) | Flagged in missing info, `LOCATION_UNVERIFIED` in flags | **PASS** |
| **5** | Contradictory / Incomplete Report | Gaps identified, uncertainty flags populated | **PASS** |
| **6** | Fallback Resilience | Deterministic engine activates without error when API is stressed | **PASS** |
| **7** | Session History & Retrieval | All processed incidents stored and retrievable by ID | **PASS** |
| **8** | Agent Trace Audit | 5 execution traces recorded with millisecond duration and model details | **PASS** |
| **9** | Human Operator Review | Decision recorded with legal non-dispatch disclaimer | **PASS** |

### Live Uvicorn HTTP Server Test
The background Uvicorn server was probed over HTTP socket on port 8000:
- `GET http://localhost:8000/api/health` ➔ `200 OK` (Healthy, Provider: Gemini)
- `POST http://localhost:8000/api/incidents` ➔ `201 Created` (`INC-001` processed)
- `GET http://localhost:8000/api/incidents/INC-001/trace` ➔ `200 OK` (5 traces verified)
- `POST http://localhost:8000/api/incidents/INC-001/review` ➔ `200 OK` (Approved)

---

## 7. How to Run and Interact with ResQAI

### 1. Server Status
The server is currently **running live in the background** on:
- **Base URL:** `http://localhost:8000`
- **Swagger UI:** `http://localhost:8000/docs`
- **Health Check:** `http://localhost:8000/api/health`

### 2. Manual Server Startup (if restarted)
From `c:\Users\shiva\Desktop\hackathon`:
```bash
uvicorn app.main:app --reload --port 8000
```

### 3. Sample cURL Invocations

#### Submit an Incident:
```bash
curl -X POST http://localhost:8000/api/incidents \
  -H "Content-Type: application/json" \
  -d "{\"report\": \"Flood near school. Two people injured.\"}"
```

#### View Execution Trace:
```bash
curl -X GET http://localhost:8000/api/incidents/INC-001/trace
```

#### Record Human Review:
```bash
curl -X POST http://localhost:8000/api/incidents/INC-001/review \
  -H "Content-Type: application/json" \
  -d "{\"decision\": \"approve\", \"reviewer_notes\": \"Operator verified situation.\", \"reviewer_id\": \"dispatcher_01\"}"
```

---

## 8. Conclusion

The ResQAI backend MVP has been fully implemented, integrated with the live Google Gemini API, verified against all edge cases, and documented. It stands ready for frontend UI integration and hackathon presentation.
