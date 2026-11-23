from typing import List, Optional, Dict, Any, Literal
from pydantic import BaseModel, Field, field_validator

# Request Models
class IncidentCreateRequest(BaseModel):
    report: str = Field(..., max_length=10000, description="Unstructured emergency text report")

    @field_validator("report")
    @classmethod
    def validate_report(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Emergency report cannot be empty.")
        return value

class HumanReviewRequest(BaseModel):
    decision: Literal["approve", "reject"] = Field(..., description="Reviewer decision")
    reviewer_notes: Optional[str] = Field(default="", description="Operator or dispatcher notes")
    reviewer_id: Optional[str] = Field(default="operator_on_duty", description="Reviewer identifier")

# Phase 2: Location and Transcript Request Models
class LocationUpdateRequest(BaseModel):
    latitude: float = Field(..., ge=-90, le=90, description="Latitude in decimal degrees")
    longitude: float = Field(..., ge=-180, le=180, description="Longitude in decimal degrees")
    accuracy: Optional[float] = Field(default=None, ge=0, description="Accuracy in meters")
    source: Literal["browser_gps", "manual_pin", "manual_text", "unknown"] = Field(
        ..., description="Source of location data"
    )
    timestamp: str = Field(..., description="ISO 8601 timestamp when location was captured")

class TranscriptUpdateRequest(BaseModel):
    transcript: str = Field(..., max_length=10000, description="Voice transcript text")
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0, description="Speech recognition confidence score")

# Internal Agent Schema Models
class IncidentRecord(BaseModel):
    category: str = Field(default="Unknown", description="Incident category (e.g. Flood, Fire, Medical, Hazmat)")
    location: str = Field(default="Unknown / Unspecified", description="Extracted location or landmark")
    affected_people: Optional[int] = Field(default=None, description="Number of affected individuals if reported")
    injuries_reported: bool = Field(default=False, description="Whether injuries are explicitly reported")
    hazards: List[str] = Field(default_factory=list, description="Identified hazards or environmental threats")
    missing_information: List[str] = Field(default_factory=list, description="Critical missing details")
    notes: Optional[str] = Field(default="", description="Intake summary notes")

class TriageRecord(BaseModel):
    priority: Literal["Critical", "High", "Medium", "Low"] = Field(
        default="Medium", description="Provisional priority assessment"
    )
    reasoning: str = Field(..., description="Detailed justification for priority rating")
    urgency_indicators: List[str] = Field(default_factory=list, description="Indicators driving urgency")
    uncertainty_flags: List[str] = Field(default_factory=list, description="Flags for missing or ambiguous info")
    missing_information: List[str] = Field(default_factory=list, description="Information gaps affecting triage")
    disclaimer: str = Field(
        default="Provisional AI assessment only; not an official emergency severity classification.",
        description="Mandatory advisory disclaimer"
    )

class ResourceItem(BaseModel):
    resource_id: str
    name: str
    resource_type: str
    location: str
    description: str
    source: str
    last_updated: str
    availability_status: str
    match_reason: str = Field(default="", description="Reason for matching this resource")
    evidence: List[str] = Field(default_factory=list, description="Evidence supporting the match")

class PlanAction(BaseModel):
    step: int = Field(..., description="Sequential step number")
    action: str = Field(..., description="Description of the action")
    action_type: Literal["safety_guidance", "professional_judgment_action"] = Field(
        ..., description="Separation between public safety guidance and responder action"
    )
    rationale: str = Field(..., description="Reason why this action is recommended")
    assigned_resource_id: Optional[str] = Field(
        default=None, description="Referenced resource ID if applicable"
    )
    target: str = Field(..., description="Target party (e.g., Public, EMS, Rescue Team, Incident Commander)")

class VerificationData(BaseModel):
    status: str = Field(default="human_review_required")
    human_review_required: bool = Field(default=True)
    flags: List[str] = Field(default_factory=list)
    unsupported_claims: List[str] = Field(default_factory=list)
    missing_evidence: List[str] = Field(default_factory=list)
    contradictions: List[str] = Field(default_factory=list)
    verified_resource_ids: List[str] = Field(default_factory=list)

class AgentTraceItem(BaseModel):
    agent: str
    status: Literal["completed", "failed", "pending", "skipped"]
    model: str
    duration_ms: float
    summary: str
    details: Optional[Dict[str, Any]] = None
    error: Optional[str] = None

class HumanReviewRecord(BaseModel):
    reviewed: bool = False
    decision: Optional[str] = None
    reviewer_notes: Optional[str] = None
    reviewer_id: Optional[str] = None
    reviewed_at: Optional[str] = None
    plan_version: Optional[int] = None
    dispatch_authorization_disclaimer: str = (
        "Human review recorded. This approval is an advisory decision-support record "
        "and does NOT constitute official emergency dispatch authorization."
    )

class LocationData(BaseModel):
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    accuracy: Optional[float] = None
    source: str = "unknown"
    timestamp: Optional[str] = None

class HazardAssessment(BaseModel):
    status: str = "unknown_due_to_coverage_or_missing_data"
    source: Optional[str] = None
    date: Optional[str] = None
    coverage: Optional[str] = None
    hazard_type: Optional[str] = None
    inside_polygon: Optional[bool] = None
    location_lat: Optional[float] = None
    location_lon: Optional[float] = None
    polygon_id: Optional[str] = None

class RescuePlan(BaseModel):
    id: str = ""
    incident_id: str = ""
    version: int = 1
    plan_json: Dict[str, Any] = {}
    assumptions: List[str] = []
    evidence_references: List[str] = []
    verification_result: Dict[str, Any] = {}
    created_at: Optional[str] = None
    invalidated_at: Optional[str] = None

class DispatchRequest(BaseModel):
    id: int
    incident_id: str
    plan_id: str
    resource_category: str
    quantity: int
    status: str
    rationale: str
    is_simulated: bool = True
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

class AuditEvent(BaseModel):
    id: int
    incident_id: str
    actor: str
    action: str
    details: Dict[str, Any] = {}
    timestamp: Optional[str] = None

# Exact API Contract Response Model
class IncidentResponse(BaseModel):
    incident_id: str
    category: str
    priority: str
    location: str
    affected_people: Optional[int] = None
    injuries_reported: bool
    missing_information: List[str]
    agents: Dict[str, str]
    resources: List[Dict[str, Any]]
    action_plan: List[Dict[str, Any]]
    verification: Dict[str, Any]
    # Supplementary fields permitted by contract: "Include any additional useful fields without renaming the agreed fields."
    raw_report: Optional[str] = None
    created_at: Optional[str] = None
    trace: Optional[List[AgentTraceItem]] = None
    human_review: Optional[HumanReviewRecord] = None
    location_data: Optional[LocationData] = None
    hazard_assessment: Optional[HazardAssessment] = None
    rescue_plan: Optional[RescuePlan] = None
    dispatch_requests: List[Dict[str, Any]] = []
    disclaimer: str = (
        "ResQAI is an experimental AI decision-support prototype. "
        "It is NOT an official emergency dispatch system and cannot authorize or dispatch emergency services."
    )

class HealthCheckResponse(BaseModel):
    status: str
    timestamp: str
    active_provider: str
    available_resources_count: int
    system_version: str = "1.0.0"
    disclaimer: str = "ResQAI Decision Support System (Non-dispatch prototype)"