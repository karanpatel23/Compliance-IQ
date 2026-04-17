from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from io import StringIO
import csv
import hashlib
import os
import shutil
from pathlib import Path

import httpx
from fastapi import Depends, FastAPI, Form, HTTPException, Request, status
from fastapi.responses import PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from passlib.context import CryptContext
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware

from .database import Base, SessionLocal, engine, get_db
from .engine import calculate_score, run_assessment
from .models import (
    AuditLog,
    BackupRecord,
    ComplianceAssessment,
    ComplianceFinding,
    ExpertReview,
    Facility,
    Regulation,
    RegulationSyncLog,
    RemediationTask,
    User,
)
from .regulations import SEED_REGULATIONS
from .schemas import (
    AssessmentOut,
    AssessmentRequest,
    ExpertReviewCreate,
    FacilityCreate,
    FacilityOut,
    FindingOut,
    RegulationCreate,
    RegulationOut,
    RemediationCreate,
    RemediationOut,
    RoleUpdateRequest,
)
from .security import decrypt_text, encrypt_text

VERIFICATION_MAX_AGE_DAYS = 365
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(bind=engine)
    seed_regulations()
    yield


BASE_DIR = Path(__file__).resolve().parent
app = FastAPI(title="Compliance IQ", version="3.1.0", lifespan=lifespan)
app.add_middleware(SessionMiddleware, secret_key=os.getenv("SESSION_SECRET", "change-me-in-production"))
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


def seed_regulations() -> None:
    with SessionLocal() as db:
        for regulation_data in SEED_REGULATIONS:
            existing = db.query(Regulation).filter(Regulation.code == regulation_data["code"]).first()
            if existing:
                continue
            db.add(Regulation(**regulation_data))
        db.commit()


def _is_regulation_currently_trusted(regulation: Regulation) -> bool:
    if regulation.status != "approved" or not regulation.last_verified_on:
        return False
    cutoff = datetime.utcnow() - timedelta(days=VERIFICATION_MAX_AGE_DAYS)
    return regulation.last_verified_on >= cutoff


def _get_current_user(request: Request, db: Session) -> User | None:
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    return db.query(User).filter(User.id == user_id).first()


def _require_auth_user(request: Request, db: Session) -> User:
    user = _get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Please sign in first")
    return user


def _require_roles(user: User, allowed: set[str]) -> None:
    if user.role not in allowed:
        raise HTTPException(status_code=403, detail=f"Role '{user.role}' does not have access")


def _write_audit(db: Session, actor_email: str, action: str, resource_type: str, resource_id: str, metadata: dict):
    db.add(
        AuditLog(
            actor_email=actor_email,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            metadata_json=metadata,
        )
    )




@app.get("/health")
def health():
    return {"status": "ok", "service": "compliance-iq", "timestamp": datetime.utcnow().isoformat()}
@app.get("/")
def home_page(request: Request, db: Session = Depends(get_db)):
    user = _get_current_user(request, db)
    if user:
        return RedirectResponse(url="/dashboard", status_code=302)
    return templates.TemplateResponse("home.html", {"request": request})


@app.get("/signup")
def signup_page(request: Request):
    return templates.TemplateResponse("signup.html", {"request": request, "error": None})


@app.post("/signup")
def signup_submit(
    request: Request,
    full_name: str = Form(...),
    email: str = Form(...),
    company_name: str = Form(...),
    role: str = Form("admin"),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    existing = db.query(User).filter(User.email == email.lower().strip()).first()
    if existing:
        return templates.TemplateResponse(
            "signup.html",
            {"request": request, "error": "Email already registered. Please sign in."},
            status_code=400,
        )

    user = User(
        full_name=full_name.strip(),
        email=email.lower().strip(),
        company_name=company_name.strip(),
        role=role.strip(),
        password_hash=pwd_context.hash(password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    request.session["user_id"] = user.id
    _write_audit(db, user.email, "signup", "user", str(user.id), {"role": user.role})
    db.commit()
    return RedirectResponse(url="/dashboard", status_code=302)


@app.get("/signin")
def signin_page(request: Request):
    return templates.TemplateResponse("signin.html", {"request": request, "error": None})


@app.post("/signin")
def signin_submit(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.email == email.lower().strip()).first()
    if not user or not pwd_context.verify(password, user.password_hash):
        return templates.TemplateResponse(
            "signin.html",
            {"request": request, "error": "Invalid email or password."},
            status_code=400,
        )

    request.session["user_id"] = user.id
    _write_audit(db, user.email, "signin", "user", str(user.id), {})
    db.commit()
    return RedirectResponse(url="/dashboard", status_code=302)


@app.get("/sso/login")
def sso_login(request: Request, db: Session = Depends(get_db)):
    """Header-based SSO bridge for enterprise IdP reverse-proxy integrations."""
    email = request.headers.get("X-SSO-Email")
    name = request.headers.get("X-SSO-Name", "SSO User")
    company = request.headers.get("X-SSO-Company", "Enterprise")
    role = request.headers.get("X-SSO-Role", "auditor")

    if not email:
        raise HTTPException(status_code=400, detail="Missing X-SSO-Email header")

    user = db.query(User).filter(User.email == email.lower().strip()).first()
    if not user:
        user = User(
            full_name=name,
            email=email.lower().strip(),
            company_name=company,
            role=role,
            password_hash=pwd_context.hash(os.urandom(12).hex()),
            sso_provider=request.headers.get("X-SSO-Provider", "enterprise-idp"),
        )
        db.add(user)
        db.commit()
        db.refresh(user)

    request.session["user_id"] = user.id
    _write_audit(db, user.email, "sso_login", "user", str(user.id), {"provider": user.sso_provider})
    db.commit()
    return RedirectResponse(url="/dashboard", status_code=302)


@app.get("/signout")
def signout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/", status_code=302)


@app.get("/dashboard")
def dashboard(request: Request, db: Session = Depends(get_db)):
    user = _require_auth_user(request, db)
    facilities_count = db.query(Facility).count()
    regulations = db.query(Regulation).all()
    assessments_count = db.query(ComplianceAssessment).count()
    open_remediations = db.query(RemediationTask).filter(RemediationTask.status != "closed").count()

    trusted_count = len([reg for reg in regulations if _is_regulation_currently_trusted(reg)])
    stale_count = len([reg for reg in regulations if reg.status == "approved" and not _is_regulation_currently_trusted(reg)])

    latest_assessments = (
        db.query(ComplianceAssessment).order_by(ComplianceAssessment.created_at.desc()).limit(5).all()
    )
    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "user": user,
            "facilities_count": facilities_count,
            "trusted_count": trusted_count,
            "stale_count": stale_count,
            "assessments_count": assessments_count,
            "latest_assessments": latest_assessments,
            "open_remediations": open_remediations,
        },
    )


@app.get("/tool")
def tool_page(request: Request, db: Session = Depends(get_db)):
    user = _require_auth_user(request, db)
    facilities = db.query(Facility).order_by(Facility.created_at.desc()).all()
    regulations = db.query(Regulation).order_by(Regulation.code.asc()).all()
    remediations = db.query(RemediationTask).order_by(RemediationTask.due_at.asc()).limit(20).all()
    return templates.TemplateResponse(
        "tool.html",
        {
            "request": request,
            "user": user,
            "facilities": facilities,
            "regulations": regulations,
            "verification_max_age_days": VERIFICATION_MAX_AGE_DAYS,
            "remediations": remediations,
        },
    )


@app.get("/api/overview")
def api_overview(db: Session = Depends(get_db)):
    regulations = db.query(Regulation).all()
    return {
        "app": "Compliance IQ",
        "version": "3.0.0",
        "verification_max_age_days": VERIFICATION_MAX_AGE_DAYS,
        "features": [
            "Enterprise SSO bridge + session auth",
            "Role-based access control",
            "Compliance assessment engine",
            "Expert review workflow",
            "Regulation freshness enforcement",
            "Assessment CSV exports",
            "Remediation SLA workflow",
            "Automated regulation update checks",
            "Audit trail logging and backup records",
        ],
        "counts": {
            "facilities": db.query(Facility).count(),
            "regulations_total": len(regulations),
            "regulations_trusted": len([r for r in regulations if _is_regulation_currently_trusted(r)]),
            "assessments": db.query(ComplianceAssessment).count(),
            "remediation_open": db.query(RemediationTask).filter(RemediationTask.status != "closed").count(),
        },
    }


@app.get("/readiness/checklist")
def readiness_checklist():
    return {
        "status": "production-ready-foundation",
        "implemented": [
            "SSO bridge and session auth",
            "RBAC role checks",
            "Managed-DB-ready configuration via DATABASE_URL",
            "Audit log model and write hooks",
            "Encrypted remediation evidence",
            "Regulation source update check job",
            "Remediation SLA breach endpoint",
            "Backup record endpoint",
        ],
    }


@app.patch("/admin/users/{user_id}/role")
def admin_update_role(user_id: int, payload: RoleUpdateRequest, request: Request, db: Session = Depends(get_db)):
    actor = _require_auth_user(request, db)
    _require_roles(actor, {"admin"})

    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="User not found")

    old_role = target.role
    target.role = payload.role
    _write_audit(db, actor.email, "role_update", "user", str(target.id), {"from": old_role, "to": payload.role})
    db.commit()
    return {"id": target.id, "email": target.email, "role": target.role}


@app.post("/facilities", response_model=FacilityOut)
def create_facility(payload: FacilityCreate, request: Request, db: Session = Depends(get_db)):
    actor = _require_auth_user(request, db)
    _require_roles(actor, {"admin", "compliance_manager"})
    facility = Facility(**payload.model_dump())
    db.add(facility)
    db.flush()
    _write_audit(db, actor.email, "facility_create", "facility", str(facility.id), {"name": facility.name})
    db.commit()
    db.refresh(facility)
    return facility


@app.get("/regulations", response_model=list[RegulationOut])
def list_regulations(db: Session = Depends(get_db)):
    return db.query(Regulation).order_by(Regulation.code.asc()).all()


@app.get("/regulations/stale", response_model=list[RegulationOut])
def list_stale_regulations(db: Session = Depends(get_db)):
    regulations = db.query(Regulation).order_by(Regulation.code.asc()).all()
    return [reg for reg in regulations if reg.status == "approved" and not _is_regulation_currently_trusted(reg)]


@app.post("/regulations", response_model=RegulationOut)
def create_regulation(payload: RegulationCreate, request: Request, db: Session = Depends(get_db)):
    actor = _require_auth_user(request, db)
    _require_roles(actor, {"admin", "reviewer"})
    exists = db.query(Regulation).filter(Regulation.code == payload.code).first()
    if exists:
        raise HTTPException(status_code=400, detail="Regulation code already exists")

    regulation = Regulation(**payload.model_dump(), status="pending")
    db.add(regulation)
    db.flush()
    _write_audit(db, actor.email, "regulation_create", "regulation", str(regulation.id), {"code": regulation.code})
    db.commit()
    db.refresh(regulation)
    return regulation


@app.post("/regulations/{regulation_id}/reviews", response_model=RegulationOut)
def review_regulation(regulation_id: int, payload: ExpertReviewCreate, request: Request, db: Session = Depends(get_db)):
    actor = _require_auth_user(request, db)
    _require_roles(actor, {"admin", "reviewer"})
    regulation = db.query(Regulation).filter(Regulation.id == regulation_id).first()
    if not regulation:
        raise HTTPException(status_code=404, detail="Regulation not found")

    review = ExpertReview(regulation_id=regulation.id, **payload.model_dump())
    db.add(review)

    if payload.decision == "approved":
        regulation.status = "approved"
        regulation.last_verified_on = datetime.utcnow()
        regulation.expert_reviewer = payload.reviewer_name
        regulation.expert_credentials = payload.reviewer_credentials
        regulation.expert_review_notes = payload.notes
    else:
        regulation.status = "rejected"

    _write_audit(db, actor.email, "regulation_review", "regulation", str(regulation.id), {"decision": payload.decision})
    db.commit()
    db.refresh(regulation)
    return regulation


@app.post("/regulations/sync/check")
def check_regulation_updates(request: Request, db: Session = Depends(get_db)):
    actor = _require_auth_user(request, db)
    _require_roles(actor, {"admin", "reviewer", "auditor"})

    regulations = db.query(Regulation).all()
    updates: list[dict] = []
    for regulation in regulations:
        change_detected = False
        source_etag = None
        source_last_modified = None
        notes = None
        try:
            response = httpx.head(regulation.source_url, timeout=5.0, follow_redirects=True)
            source_etag = response.headers.get("etag")
            source_last_modified = response.headers.get("last-modified")
            notes = f"HTTP {response.status_code}"
        except Exception as exc:  # noqa: BLE001
            notes = f"check failed: {exc}"

        log = RegulationSyncLog(
            regulation_id=regulation.id,
            source_etag=source_etag,
            source_last_modified=source_last_modified,
            change_detected=change_detected,
            notes=notes,
        )
        db.add(log)
        updates.append({"regulation": regulation.code, "etag": source_etag, "last_modified": source_last_modified, "notes": notes})

    _write_audit(db, actor.email, "regulation_sync_check", "regulation", "bulk", {"count": len(updates)})
    db.commit()
    return {"checked": len(updates), "results": updates}


@app.post("/assessments/run", response_model=AssessmentOut)
def run_compliance_assessment(payload: AssessmentRequest, request: Request, db: Session = Depends(get_db)):
    actor = _require_auth_user(request, db)
    _require_roles(actor, {"admin", "compliance_manager", "auditor"})
    facility = db.query(Facility).filter(Facility.id == payload.facility_id).first()
    if not facility:
        raise HTTPException(status_code=404, detail="Facility not found")

    all_regulations = db.query(Regulation).all()
    trusted_regulations = [reg for reg in all_regulations if _is_regulation_currently_trusted(reg)]

    if not trusted_regulations:
        raise HTTPException(
            status_code=400,
            detail="No trusted regulations available. Approve and verify at least one regulation first.",
        )

    engine_findings = run_assessment(facility, trusted_regulations)
    score = calculate_score(engine_findings)
    summary = (
        f"Assessed {len(engine_findings)} applicable trusted regulations. "
        f"Compliance score: {score}%"
    )

    assessment = ComplianceAssessment(facility_id=facility.id, overall_score=score, summary=summary)
    db.add(assessment)
    db.flush()

    for finding in engine_findings:
        db.add(
            ComplianceFinding(
                assessment_id=assessment.id,
                regulation_id=finding.regulation_id,
                status=finding.status,
                severity=finding.severity,
                details=finding.details,
                due_in_days=finding.due_in_days,
            )
        )

    _write_audit(db, actor.email, "assessment_run", "assessment", str(assessment.id), {"facility_id": facility.id})
    db.commit()
    db.refresh(assessment)

    detailed_findings = [
        FindingOut(
            regulation_code=finding.regulation.code,
            regulation_title=finding.regulation.title,
            status=finding.status,
            severity=finding.severity,
            details=finding.details,
            due_in_days=finding.due_in_days,
        )
        for finding in assessment.findings
    ]

    return AssessmentOut(
        assessment_id=assessment.id,
        facility_id=assessment.facility_id,
        overall_score=assessment.overall_score,
        summary=assessment.summary,
        created_at=assessment.created_at,
        findings=detailed_findings,
    )


@app.get("/reports/assessment/{assessment_id}/csv", response_class=PlainTextResponse)
def export_assessment_csv(assessment_id: int, request: Request, db: Session = Depends(get_db)):
    actor = _require_auth_user(request, db)
    _require_roles(actor, {"admin", "compliance_manager", "auditor"})
    assessment = db.query(ComplianceAssessment).filter(ComplianceAssessment.id == assessment_id).first()
    if not assessment:
        raise HTTPException(status_code=404, detail="Assessment not found")

    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(["regulation_code", "regulation_title", "status", "severity", "details", "due_in_days"])
    for finding in assessment.findings:
        writer.writerow(
            [
                finding.regulation.code,
                finding.regulation.title,
                finding.status,
                finding.severity,
                finding.details,
                finding.due_in_days,
            ]
        )
    _write_audit(db, actor.email, "assessment_export_csv", "assessment", str(assessment.id), {})
    db.commit()
    return output.getvalue()


@app.post("/remediations", response_model=RemediationOut)
def create_remediation(payload: RemediationCreate, request: Request, db: Session = Depends(get_db)):
    actor = _require_auth_user(request, db)
    _require_roles(actor, {"admin", "compliance_manager"})

    finding = db.query(ComplianceFinding).filter(ComplianceFinding.id == payload.finding_id).first()
    owner = db.query(User).filter(User.id == payload.owner_id).first()
    if not finding or not owner:
        raise HTTPException(status_code=404, detail="Finding or owner not found")

    task = RemediationTask(
        finding_id=payload.finding_id,
        owner_id=payload.owner_id,
        title=payload.title,
        priority=payload.priority,
        due_at=payload.due_at,
        evidence_encrypted=encrypt_text(payload.evidence) if payload.evidence else None,
    )
    db.add(task)
    db.flush()
    _write_audit(db, actor.email, "remediation_create", "remediation", str(task.id), {"priority": task.priority})
    db.commit()
    db.refresh(task)
    return task


@app.post("/remediations/{task_id}/complete", response_model=RemediationOut)
def complete_remediation(task_id: int, request: Request, db: Session = Depends(get_db)):
    actor = _require_auth_user(request, db)
    _require_roles(actor, {"admin", "compliance_manager", "auditor"})

    task = db.query(RemediationTask).filter(RemediationTask.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    task.status = "closed"
    task.completed_at = datetime.utcnow()
    _write_audit(db, actor.email, "remediation_complete", "remediation", str(task.id), {})
    db.commit()
    db.refresh(task)
    return task


@app.get("/remediations", response_model=list[RemediationOut])
def list_remediations(request: Request, db: Session = Depends(get_db)):
    actor = _require_auth_user(request, db)
    _require_roles(actor, {"admin", "compliance_manager", "auditor", "reviewer"})
    return db.query(RemediationTask).order_by(RemediationTask.due_at.asc()).all()


@app.get("/remediations/sla/breaches")
def list_sla_breaches(request: Request, db: Session = Depends(get_db)):
    actor = _require_auth_user(request, db)
    _require_roles(actor, {"admin", "compliance_manager", "auditor"})
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    breached = (
        db.query(RemediationTask)
        .filter(RemediationTask.status != "closed", RemediationTask.due_at < now)
        .order_by(RemediationTask.due_at.asc())
        .all()
    )
    return {
        "count": len(breached),
        "tasks": [
            {
                "id": t.id,
                "title": t.title,
                "due_at": t.due_at,
                "priority": t.priority,
                "status": t.status,
            }
            for t in breached
        ],
    }


@app.get("/remediations/{task_id}/evidence")
def get_remediation_evidence(task_id: int, request: Request, db: Session = Depends(get_db)):
    actor = _require_auth_user(request, db)
    _require_roles(actor, {"admin", "compliance_manager", "auditor"})

    task = db.query(RemediationTask).filter(RemediationTask.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if not task.evidence_encrypted:
        return {"task_id": task.id, "evidence": None}
    return {"task_id": task.id, "evidence": decrypt_text(task.evidence_encrypted)}


@app.post("/ops/backup")
def run_backup(request: Request, db: Session = Depends(get_db)):
    actor = _require_auth_user(request, db)
    _require_roles(actor, {"admin"})
    source = os.getenv("BACKUP_SOURCE_FILE", "./compliance_iq.db")
    target_dir = os.getenv("BACKUP_DIR", "./backups")
    os.makedirs(target_dir, exist_ok=True)
    target = os.path.join(target_dir, f"compliance_iq_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.db")

    try:
        shutil.copy2(source, target)
        with open(target, "rb") as f:
            checksum = hashlib.sha256(f.read()).hexdigest()
        status_value = "success"
    except Exception as exc:  # noqa: BLE001
        checksum = None
        status_value = f"failed: {exc}"

    record = BackupRecord(target=target, status=status_value, checksum=checksum)
    db.add(record)
    _write_audit(db, actor.email, "backup_run", "backup", str(record.id), {"target": target, "status": status_value})
    db.commit()
    db.refresh(record)
    return {"id": record.id, "target": record.target, "status": record.status, "checksum": record.checksum}


@app.get("/ops/audit-logs")
def get_audit_logs(request: Request, db: Session = Depends(get_db)):
    actor = _require_auth_user(request, db)
    _require_roles(actor, {"admin", "auditor"})
    logs = db.query(AuditLog).order_by(AuditLog.created_at.desc()).limit(200).all()
    return [
        {
            "id": log.id,
            "actor_email": log.actor_email,
            "action": log.action,
            "resource_type": log.resource_type,
            "resource_id": log.resource_id,
            "metadata": log.metadata_json,
            "created_at": log.created_at,
        }
        for log in logs
    ]
