from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    company_name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(100), default="admin")
    sso_provider: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Facility(Base):
    __tablename__ = "facilities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    sector: Mapped[str] = mapped_column(String(100), nullable=False)
    state: Mapped[str] = mapped_column(String(2), nullable=False)
    employees: Mapped[int] = mapped_column(Integer, nullable=False)
    annual_hazardous_waste_kg: Mapped[float] = mapped_column(Float, default=0)
    stores_hazardous_chemicals: Mapped[bool] = mapped_column(Boolean, default=False)
    produces_human_food: Mapped[bool] = mapped_column(Boolean, default=False)
    has_lockout_program: Mapped[bool] = mapped_column(Boolean, default=False)
    has_sds_program: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    assessments: Mapped[list["ComplianceAssessment"]] = relationship(back_populates="facility")


class Regulation(Base):
    __tablename__ = "regulations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    code: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    authority: Mapped[str] = mapped_column(String(100), nullable=False)
    applies_to_sector: Mapped[str] = mapped_column(String(100), default="all")
    criteria: Mapped[dict] = mapped_column(JSON, nullable=False)
    required_actions: Mapped[list] = mapped_column(JSON, nullable=False)
    source_url: Mapped[str] = mapped_column(String(500), nullable=False)
    source_name: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    version: Mapped[str] = mapped_column(String(20), default="1.0")
    last_verified_on: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    expert_reviewer: Mapped[str | None] = mapped_column(String(200), nullable=True)
    expert_credentials: Mapped[str | None] = mapped_column(String(300), nullable=True)
    expert_review_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    findings: Mapped[list["ComplianceFinding"]] = relationship(back_populates="regulation")
    reviews: Mapped[list["ExpertReview"]] = relationship(back_populates="regulation")
    sync_logs: Mapped[list["RegulationSyncLog"]] = relationship(back_populates="regulation")


class ComplianceAssessment(Base):
    __tablename__ = "assessments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    facility_id: Mapped[int] = mapped_column(ForeignKey("facilities.id"), nullable=False)
    overall_score: Mapped[float] = mapped_column(Float, nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    facility: Mapped[Facility] = relationship(back_populates="assessments")
    findings: Mapped[list["ComplianceFinding"]] = relationship(back_populates="assessment")


class ComplianceFinding(Base):
    __tablename__ = "findings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    assessment_id: Mapped[int] = mapped_column(ForeignKey("assessments.id"), nullable=False)
    regulation_id: Mapped[int] = mapped_column(ForeignKey("regulations.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    details: Mapped[str] = mapped_column(Text, nullable=False)
    due_in_days: Mapped[int] = mapped_column(Integer, default=30)

    assessment: Mapped[ComplianceAssessment] = relationship(back_populates="findings")
    regulation: Mapped[Regulation] = relationship(back_populates="findings")
    remediation_tasks: Mapped[list["RemediationTask"]] = relationship(back_populates="finding")


class ExpertReview(Base):
    __tablename__ = "expert_reviews"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    regulation_id: Mapped[int] = mapped_column(ForeignKey("regulations.id"), nullable=False)
    reviewer_name: Mapped[str] = mapped_column(String(200), nullable=False)
    reviewer_credentials: Mapped[str] = mapped_column(String(300), nullable=False)
    decision: Mapped[str] = mapped_column(String(20), nullable=False)
    notes: Mapped[str] = mapped_column(Text, nullable=False)
    reviewed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    regulation: Mapped[Regulation] = relationship(back_populates="reviews")


class RemediationTask(Base):
    __tablename__ = "remediation_tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    finding_id: Mapped[int] = mapped_column(ForeignKey("findings.id"), nullable=False)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="open")
    priority: Mapped[str] = mapped_column(String(20), default="high")
    due_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    evidence_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    finding: Mapped[ComplianceFinding] = relationship(back_populates="remediation_tasks")


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    actor_email: Mapped[str] = mapped_column(String(255), nullable=False)
    action: Mapped[str] = mapped_column(String(120), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(100), nullable=False)
    resource_id: Mapped[str] = mapped_column(String(120), nullable=False)
    metadata_json: Mapped[dict] = mapped_column(JSON, default={})
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class RegulationSyncLog(Base):
    __tablename__ = "regulation_sync_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    regulation_id: Mapped[int] = mapped_column(ForeignKey("regulations.id"), nullable=False)
    checked_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    source_last_modified: Mapped[str | None] = mapped_column(String(120), nullable=True)
    source_etag: Mapped[str | None] = mapped_column(String(120), nullable=True)
    change_detected: Mapped[bool] = mapped_column(Boolean, default=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    regulation: Mapped[Regulation] = relationship(back_populates="sync_logs")


class BackupRecord(Base):
    __tablename__ = "backup_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    target: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    checksum: Mapped[str | None] = mapped_column(String(80), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
