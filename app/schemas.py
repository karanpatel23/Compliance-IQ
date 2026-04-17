from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class FacilityCreate(BaseModel):
    name: str
    sector: str
    state: str = Field(min_length=2, max_length=2)
    employees: int = Field(ge=1)
    annual_hazardous_waste_kg: float = Field(ge=0)
    stores_hazardous_chemicals: bool = False
    produces_human_food: bool = False
    has_lockout_program: bool = False
    has_sds_program: bool = False


class FacilityOut(FacilityCreate):
    id: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class RegulationCreate(BaseModel):
    code: str
    title: str
    authority: str
    applies_to_sector: str = "all"
    criteria: dict
    required_actions: list[str]
    source_url: str
    source_name: str
    version: str = "1.0"


class RegulationOut(BaseModel):
    id: int
    code: str
    title: str
    authority: str
    applies_to_sector: str
    status: str
    source_url: str
    source_name: str
    last_verified_on: datetime | None
    expert_reviewer: str | None

    model_config = ConfigDict(from_attributes=True)


class ExpertReviewCreate(BaseModel):
    reviewer_name: str
    reviewer_credentials: str
    decision: str = Field(pattern="^(approved|rejected)$")
    notes: str


class AssessmentRequest(BaseModel):
    facility_id: int


class FindingOut(BaseModel):
    regulation_code: str
    regulation_title: str
    status: str
    severity: str
    details: str
    due_in_days: int


class AssessmentOut(BaseModel):
    assessment_id: int
    facility_id: int
    overall_score: float
    summary: str
    created_at: datetime
    findings: list[FindingOut]


class RoleUpdateRequest(BaseModel):
    role: str = Field(pattern="^(admin|compliance_manager|auditor|reviewer)$")


class RemediationCreate(BaseModel):
    finding_id: int
    owner_id: int
    title: str
    priority: str = Field(pattern="^(low|medium|high)$")
    due_at: datetime
    evidence: str | None = None


class RemediationOut(BaseModel):
    id: int
    finding_id: int
    owner_id: int
    title: str
    status: str
    priority: str
    due_at: datetime
    completed_at: datetime | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
