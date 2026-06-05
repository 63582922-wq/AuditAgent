from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(50), default="created")
    state_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    files: Mapped[List["FileRecord"]] = relationship(back_populates="project")
    risks: Mapped[List["Risk"]] = relationship(back_populates="project")
    outputs: Mapped[List["Output"]] = relationship(back_populates="project")


class FileRecord(Base):
    __tablename__ = "files"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"))
    file_name: Mapped[str] = mapped_column(String(512))
    file_type: Mapped[str] = mapped_column(String(50))
    document_category: Mapped[str] = mapped_column(String(100), default="unknown")
    storage_path: Mapped[str] = mapped_column(String(1024))
    parse_status: Mapped[str] = mapped_column(String(50), default="pending")
    confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    meta_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    project: Mapped["Project"] = relationship(back_populates="files")
    parsed_document: Mapped[Optional["ParsedDocument"]] = relationship(
        back_populates="file", uselist=False
    )


class ParsedDocument(Base):
    __tablename__ = "parsed_documents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"))
    file_id: Mapped[str] = mapped_column(ForeignKey("files.id"), unique=True)
    document_type: Mapped[str] = mapped_column(String(100))
    content_json: Mapped[Dict[str, Any]] = mapped_column(JSON)
    text_content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    file: Mapped["FileRecord"] = relationship(back_populates="parsed_document")


class ExtractedEntity(Base):
    __tablename__ = "extracted_entities"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"))
    file_id: Mapped[str] = mapped_column(ForeignKey("files.id"))
    entity_type: Mapped[str] = mapped_column(String(100))
    entity_value: Mapped[str] = mapped_column(Text)
    standard_value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source_location: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Rule(Base):
    __tablename__ = "rules"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    rule_id: Mapped[str] = mapped_column(String(50), unique=True)
    rule_name: Mapped[str] = mapped_column(String(255))
    risk_category: Mapped[str] = mapped_column(String(100))
    risk_level: Mapped[str] = mapped_column(String(20))
    applicable_document_type: Mapped[str] = mapped_column(String(100))
    condition_json: Mapped[Dict[str, Any]] = mapped_column(JSON)
    evidence_fields: Mapped[List[Any]] = mapped_column(JSON, default=list)
    suggestion_template: Mapped[str] = mapped_column(Text)
    manual_review_required: Mapped[bool] = mapped_column(Boolean, default=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    priority: Mapped[int] = mapped_column(Integer, default=100)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class Risk(Base):
    __tablename__ = "risks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"))
    risk_id: Mapped[str] = mapped_column(String(50))
    risk_category: Mapped[str] = mapped_column(String(100))
    risk_subcategory: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    risk_level: Mapped[str] = mapped_column(String(20))
    risk_score: Mapped[int] = mapped_column(Integer, default=0)
    source_file_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    source_location_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    related_files: Mapped[Optional[List[Any]]] = mapped_column(JSON, nullable=True)
    problem: Mapped[str] = mapped_column(Text)
    evidence_json: Mapped[Dict[str, Any]] = mapped_column(JSON)
    rule_triggered: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    analysis: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    suggestion: Mapped[str] = mapped_column(Text)
    correction_action: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    manual_review_required: Mapped[bool] = mapped_column(Boolean, default=False)
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    status: Mapped[str] = mapped_column(String(50), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    project: Mapped["Project"] = relationship(back_populates="risks")
    reviews: Mapped[List["ReviewRecord"]] = relationship(back_populates="risk")


class ReviewRecord(Base):
    __tablename__ = "review_records"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"))
    risk_id: Mapped[str] = mapped_column(ForeignKey("risks.id"))
    review_status: Mapped[str] = mapped_column(String(50))
    review_comment: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    reviewed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    risk: Mapped["Risk"] = relationship(back_populates="reviews")


class Memory(Base):
    __tablename__ = "memories"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    memory_type: Mapped[str] = mapped_column(String(100))
    content: Mapped[str] = mapped_column(Text)
    tags: Mapped[List[Any]] = mapped_column(JSON, default=list)
    embedding_json: Mapped[Optional[List[float]]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class Output(Base):
    __tablename__ = "outputs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"))
    output_type: Mapped[str] = mapped_column(String(100))
    file_name: Mapped[str] = mapped_column(String(512))
    storage_path: Mapped[str] = mapped_column(String(1024))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    project: Mapped["Project"] = relationship(back_populates="outputs")


class AgentRunLog(Base):
    __tablename__ = "agent_run_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"))
    step: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(50))
    detail_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    duration_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class AnalysisJob(Base):
    __tablename__ = "analysis_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"))
    status: Mapped[str] = mapped_column(String(50), default="queued")
    current_step: Mapped[str] = mapped_column(String(100), default="queued")
    progress_pct: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class RecordLink(Base):
    __tablename__ = "record_links"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"))
    link_type: Mapped[str] = mapped_column(String(100))
    source_file_id: Mapped[str] = mapped_column(String(36))
    target_file_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    link_keys: Mapped[Dict[str, Any]] = mapped_column(JSON)
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    match_method: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
