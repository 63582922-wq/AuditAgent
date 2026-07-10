from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ProjectCreate(BaseModel):
    name: str


class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    summary: Optional[str] = None


class ProjectBatchDelete(BaseModel):
    project_ids: list[str] = Field(default_factory=list)


class AgentChatMessage(BaseModel):
    role: str
    content: str


class AgentChatRequest(BaseModel):
    message: str
    project_id: Optional[str] = None
    meeting_id: Optional[str] = None
    history: list[AgentChatMessage] = Field(default_factory=list)


class AgentChatAction(BaseModel):
    id: str
    label: str
    description: str
    segment: str
    requires_meeting: bool = False
    requires_approval: bool = False
    proposal_id: Optional[str] = None
    tone: str = "default"


class AgentChatResponse(BaseModel):
    reply: str
    answer: str = ""
    actions: list[AgentChatAction] = Field(default_factory=list)
    planned_actions: list[AgentChatAction] = Field(default_factory=list)
    citations: list[Dict[str, Any]] = Field(default_factory=list)
    intent: str = "consult"
    mode: str
    context: Dict[str, Any] = Field(default_factory=dict)


class AgentActionApproveRequest(BaseModel):
    comment: Optional[str] = None


class AgentActionApproveResponse(BaseModel):
    ok: bool
    proposal_id: str
    action_id: str
    status: str
    message: Optional[str] = None
    job_id: Optional[str] = None


class AgentFeedbackRequest(BaseModel):
    feedback: str
    project_id: str
    meeting_id: Optional[str] = None
    original_conclusion: Optional[str] = None


class AgentFeedbackResponse(BaseModel):
    ok: bool
    proposal_id: str
    status: str
    message: str


class MeetingCreate(BaseModel):
    meeting_code: str
    meeting_title: Optional[str] = None
    observation_type: Optional[str] = None
    meeting_type: Optional[str] = None
    meeting_date: Optional[str] = None


class MeetingUpdate(BaseModel):
    meeting_code: Optional[str] = None
    meeting_title: Optional[str] = None
    observation_type: Optional[str] = None
    meeting_type: Optional[str] = None
    meeting_date: Optional[str] = None
    summary: Optional[str] = None


class MeetingBatchDelete(BaseModel):
    meeting_ids: list[str] = Field(default_factory=list)


class MeetingOut(BaseModel):
    id: str
    project_id: str
    meeting_code: str
    meeting_title: Optional[str] = None
    observation_type: Optional[str] = None
    meeting_type: Optional[str] = None
    meeting_date: Optional[str] = None
    status: str
    summary: Optional[str] = None
    state_json: Optional[Dict[str, Any]] = None
    deliverable_json: Optional[Dict[str, Any]] = None
    file_count: int = 0
    risk_count: int = 0
    output_count: int = 0
    created_at: datetime
    updated_at: datetime
    last_run_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


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
    meeting_id: Optional[str] = None
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


class DeliverableReview(BaseModel):
    comment: Optional[str] = None
    reanalyze: bool = False


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


class ProjectLiveOut(ProjectOut):
    """轻量快照：HUD / 侧栏轮询用，不含 risks/outputs 等大列表。"""
    state_json: Optional[Dict[str, Any]] = None
    file_count: int = 0
    risk_count: int = 0
    output_count: int = 0


class FileBriefOut(BaseModel):
    id: str
    file_name: str
    document_category: str
    parse_status: str

    model_config = {"from_attributes": True}


class RiskPreviewOut(BaseModel):
    id: str
    risk_level: str
    problem: str

    model_config = {"from_attributes": True}


class ProjectOverviewOut(ProjectLiveOut):
    """概览页首屏：不含完整 risk 明细与 evidence。"""
    files: List[FileBriefOut] = Field(default_factory=list)
    risk_preview: List[RiskPreviewOut] = Field(default_factory=list)


class AnalyzeResponse(BaseModel):
    project_id: str
    status: str
    message: str
    job_id: Optional[str] = None


class ReanalyzeRequest(BaseModel):
    scope: str = Field(default="adjudicating", description="cross_checking | adjudicating")


class JobOut(BaseModel):
    id: str
    project_id: str
    meeting_id: Optional[str] = None
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


class HarnessImportRequest(BaseModel):
    case_path: str
    project_name: Optional[str] = None


class HarnessRunRequest(BaseModel):
    skip_orchestrator: bool = False
    meeting_id: Optional[str] = None


class HarnessImportToProjectRequest(BaseModel):
    project_id: str
    meeting_id: Optional[str] = None


class HarnessResultOut(BaseModel):
    project_id: str
    meeting_id: str = ""
    status: str
    meeting_code: str = ""
    finding_count: int = 0
    meeting_case: Dict[str, Any] = Field(default_factory=dict)
    runtime: Dict[str, Any] = Field(default_factory=dict)
    job_id: Optional[str] = None
    message: Optional[str] = None
