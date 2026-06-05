from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ProjectCreate(BaseModel):
    name: str


class ProjectOut(BaseModel):
    id: str
    name: str
    status: str
    summary: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class FileOut(BaseModel):
    id: str
    project_id: str
    file_name: str
    file_type: str
    document_category: str
    parse_status: str
    confidence: Optional[float] = None
    meta_json: Optional[Dict[str, Any]] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class RiskOut(BaseModel):
    id: str
    project_id: str
    risk_id: str
    risk_category: str
    risk_subcategory: Optional[str] = None
    risk_level: str
    risk_score: int
    source_file_id: Optional[str] = None
    source_location_json: Optional[Dict[str, Any]] = None
    related_files: Optional[List[Any]] = None
    problem: str
    evidence_json: Dict[str, Any]
    rule_triggered: Optional[str] = None
    analysis: Optional[str] = None
    suggestion: str
    correction_action: Optional[str] = None
    manual_review_required: bool
    confidence: float
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


class ReviewCreate(BaseModel):
    review_status: str
    review_comment: Optional[str] = None


class OutputOut(BaseModel):
    id: str
    project_id: str
    output_type: str
    file_name: str
    storage_path: str
    created_at: datetime

    model_config = {"from_attributes": True}


class MemoryCreate(BaseModel):
    memory_type: str
    content: str
    tags: List[str] = Field(default_factory=list)


class MemoryOut(BaseModel):
    id: str
    memory_type: str
    content: str
    tags: List[str]
    created_at: datetime

    model_config = {"from_attributes": True}


class RuleOut(BaseModel):
    id: str
    rule_id: str
    rule_name: str
    risk_category: str
    risk_level: str
    applicable_document_type: str
    enabled: bool

    model_config = {"from_attributes": True}


class ProjectDetail(ProjectOut):
    state_json: Optional[Dict[str, Any]] = None
    files: List[FileOut] = Field(default_factory=list)
    risks: List[RiskOut] = Field(default_factory=list)
    outputs: List[OutputOut] = Field(default_factory=list)


class AnalyzeResponse(BaseModel):
    project_id: str
    status: str
    message: str
    job_id: Optional[str] = None


class JobOut(BaseModel):
    id: str
    project_id: str
    status: str
    current_step: str
    progress_pct: int
    error_message: Optional[str] = None
    created_at: datetime
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class RuleCreate(BaseModel):
    rule_id: str
    rule_name: str
    risk_category: str
    risk_level: str
    applicable_document_type: str
    condition: Dict[str, Any]
    evidence_fields: List[str] = Field(default_factory=list)
    suggestion_template: str
    manual_review_required: bool = False
    priority: int = 100


class AgentLogOut(BaseModel):
    id: str
    step: str
    status: str
    detail_json: Optional[Dict[str, Any]] = None
    duration_ms: Optional[int] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class MissingDocument(BaseModel):
    document_type: str
    importance: str
    reason: str


class ProjectSummary(BaseModel):
    total_risks: int
    high: int
    medium: int
    low: int
    missing_documents: List[Any] = Field(default_factory=list)
    correction_suggestions: List[str] = Field(default_factory=list)


class StatsOut(BaseModel):
    project_count: int
    risk_count: int
    rule_count: int
    high_count: int
    medium_count: int
    low_count: int
