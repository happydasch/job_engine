from __future__ import annotations

import json
import logging
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse
from job_engine.database import get_sync_engine as get_engine
from job_engine.models import (
    APPLICATION_STATUSES,
    Application,
    ApplicationLog,
    Job,
    as_utc,
)
from job_engine.models import (
    APPLICATION_TERMINAL_STATUSES as TERMINAL_STATUSES,
)
from job_engine.plugin import plugin_registry
from sqlalchemy.orm import Session, joinedload

from dashboard.routes.route_helpers import app_to_dict

logger = logging.getLogger(__name__)
router = APIRouter()


# ── Status machine ─────────────────────────────────────────────────────────
# APPLICATION_STATUSES and TERMINAL_STATUSES live in job_engine.models — the
# single source of truth shared with the DB's CHECK constraint.
VALID_TRANSITIONS = {
    "applied": ["interview", "offer", "accepted", "rejected", "withdrawn"],
    "interview": ["offer", "rejected", "withdrawn"],
    "offer": ["accepted", "rejected", "withdrawn"],
    "accepted": ["withdrawn"],
    "rejected": [],  # terminal
    "withdrawn": [],  # terminal
}


def _is_valid_transition(current: str, target: str) -> bool:
    """Check if a status transition is valid."""
    return target in VALID_TRANSITIONS.get(current, [])


def _archive_materials(app: Application, status: str) -> str:
    """Snapshot an application's materials to its archive folder; return the folder path."""
    archive_dir = os.path.join("data", "archives", "applications", str(app.id))
    os.makedirs(archive_dir, exist_ok=True)

    materials = {}
    if app.cover_letter:
        cover_path = os.path.join(archive_dir, "cover_letter.txt")
        with open(cover_path, "w") as f:
            f.write(app.cover_letter)
        materials["cover_letter"] = cover_path

    if app.job:
        job_path = os.path.join(archive_dir, "job_posting.txt")
        with open(job_path, "w") as f:
            f.write(app.job.title or "Untitled")
            f.write("\n\n")
            f.write(app.job.description or "")
        materials["job_posting"] = job_path

    meta_path = os.path.join(archive_dir, "metadata.json")
    with open(meta_path, "w") as f:
        json.dump(
            {
                "application_id": app.id,
                "job_id": app.job_id,
                "status": status,
                "archived_at": datetime.now(UTC).isoformat(),
                "materials": materials,
            },
            f,
            indent=2,
        )
    return archive_dir


# ── Routes ─────────────────────────────────────────────────────────────────


@router.post("/api/applications")
async def api_create_application(data: dict):
    """Create a new application for a job."""
    job_id = data.get("job_id")
    if not job_id:
        raise HTTPException(status_code=400, detail="job_id is required")

    engine = get_engine()
    with Session(engine) as session:
        job = session.query(Job).filter(Job.external_id == job_id).first()
        if job is None:
            raise HTTPException(status_code=404, detail="Job not found")

        # Check for existing (non-deleted) application
        existing = (
            session.query(Application)
            .filter(Application.job_id == job.id, Application.deleted_at.is_(None))
            .first()
        )
        if existing:
            return JSONResponse(
                {"status": "exists", "application_id": existing.id}, status_code=200
            )

        status = data.get("status", "applied")
        if status not in APPLICATION_STATUSES:
            raise HTTPException(status_code=400, detail=f"Invalid status: {status}")

        now = datetime.now(UTC)
        # Seed the cover letter from the job's cached AI analysis (if any) so
        # the application's PDF export doesn't start out empty — the same
        # letter the user already saw on the job detail page.
        cover_letter = data.get("cover_letter") or job.llm_cover_letter
        app = Application(
            job_id=job.id,
            status=status,
            applied_at=now,
            cover_letter=cover_letter,
            outcome=data.get("outcome"),
            archived_materials_path=data.get("archived_materials_path"),
        )
        session.add(app)

        # Flush to get app.id before writing log
        session.flush()

        # Write initial application log entry
        log_entry = ApplicationLog(
            application_id=app.id,
            from_status=None,
            to_status=status,
            changed_by="user",
        )
        session.add(log_entry)
        session.commit()

        # Notify plugins of the newly created application
        plugin_registry.trigger("on_application_create", app_to_dict(app))

        return JSONResponse({"status": "created", "application_id": app.id}, status_code=201)


@router.get("/api/applications")
async def api_list_applications(
    status: str = Query("", description="Filter by status"),
    job_id: int = Query(None, description="Filter by internal job ID"),
    limit: int = Query(50, description="Max results"),
):
    """List applications as JSON."""
    engine = get_engine()
    with Session(engine) as session:
        query = session.query(Application).options(
            joinedload(Application.job).joinedload(Job.company_rel)
        )
        if status:
            query = query.filter(Application.status == status)
        if job_id is not None:
            query = query.filter(Application.job_id == job_id)
        query = query.filter(Application.deleted_at.is_(None))
        apps = query.order_by(Application.updated_at.desc()).limit(limit).all()

        result = []
        for app in apps:
            job = app.job
            d = app_to_dict(app)
            d.update(
                {
                    "job_title": job.title if job else None,
                    "company": job.company_rel.name if job and job.company_rel else None,
                    "interview_at": app.interview_at.isoformat() if app.interview_at else None,
                    "offer_at": app.offer_at.isoformat() if app.offer_at else None,
                    "outcome": app.outcome,
                    "outcome_reason": app.outcome_reason,
                    "cover_letter": app.cover_letter,
                    "archived_materials_path": app.archived_materials_path,
                }
            )
            result.append(d)
        return JSONResponse(result)


@router.patch("/api/applications/{app_id}/status")
async def api_update_application_status(app_id: int, data: dict):
    """Transition an application to a new status."""
    new_status = data.get("status")
    if not new_status:
        raise HTTPException(status_code=400, detail="status is required")
    if new_status not in APPLICATION_STATUSES:
        raise HTTPException(status_code=400, detail=f"Invalid status: {new_status}")

    engine = get_engine()
    with Session(engine) as session:
        app = session.query(Application).filter(Application.id == app_id).first()
        if app is None or app.deleted_at is not None:
            raise HTTPException(status_code=404, detail="Application not found")

        if not _is_valid_transition(app.status, new_status):
            raise HTTPException(
                status_code=400,
                detail=f"Cannot transition from '{app.status}' to '{new_status}'",
            )

        old_status = app.status
        app.status = new_status
        now = datetime.now(UTC)

        # Update timestamps based on new status
        if new_status == "applied" and not app.applied_at:
            app.applied_at = now
        elif new_status == "interview":
            app.interview_at = now
        elif new_status == "offer":
            app.offer_at = now

        app.updated_at = now

        # If moving to terminal status, record outcome_reason
        outcome_reason = data.get("outcome_reason")
        if outcome_reason and new_status in ("rejected", "withdrawn", "accepted"):
            app.outcome_reason = outcome_reason

        outcome = data.get("outcome")
        if outcome:
            app.outcome = outcome

        # Snapshot materials the first time the application closes
        if new_status in TERMINAL_STATUSES and app.archived_materials_path is None:
            app.archived_materials_path = _archive_materials(app, new_status)

        # Write application log entry
        log_entry = ApplicationLog(
            application_id=app.id,
            from_status=old_status,
            to_status=new_status,
            reason=data.get("reason"),
            changed_by="user",
        )
        session.add(log_entry)
        session.commit()

        # Notify plugins of the status change
        plugin_registry.trigger(
            "on_application_status_change", app_to_dict(app), old_status, new_status
        )

        return JSONResponse(
            {
                "status": "ok",
                "application_id": app.id,
                "old_status": old_status,
                "new_status": new_status,
            }
        )


@router.post("/api/applications/{app_id}/reopen")
async def api_reopen_application(app_id: int):
    """Reopen a closed/finished application back to 'applied' status."""
    engine = get_engine()
    with Session(engine) as session:
        app = session.query(Application).filter(Application.id == app_id).first()
        if app is None or app.deleted_at is not None:
            raise HTTPException(status_code=404, detail="Application not found")

        old_status = app.status
        now = datetime.now(UTC)
        app.status = "applied"
        app.applied_at = now
        app.interview_at = None
        app.offer_at = None
        app.outcome = None
        app.outcome_reason = None
        app.updated_at = now

        log_entry = ApplicationLog(
            application_id=app.id,
            from_status=old_status,
            to_status="applied",
            changed_by="user",
        )
        session.add(log_entry)
        session.commit()

        plugin_registry.trigger(
            "on_application_status_change", app_to_dict(app), old_status, "applied"
        )

        return JSONResponse({"status": "ok", "application_id": app.id, "new_status": "applied"})


@router.get("/api/applications/{app_id}/logs")
async def api_application_logs(app_id: int):
    """Return the append-only status history for an application, oldest first."""
    engine = get_engine()
    with Session(engine) as session:
        app = session.query(Application).filter(Application.id == app_id).first()
        if app is None or app.deleted_at is not None:
            raise HTTPException(status_code=404, detail="Application not found")
        logs = (
            session.query(ApplicationLog)
            .filter(ApplicationLog.application_id == app_id)
            .order_by(ApplicationLog.created_at, ApplicationLog.id)
            .all()
        )
        return JSONResponse(
            [
                {
                    "id": log.id,
                    "from_status": log.from_status,
                    "to_status": log.to_status,
                    "changed_by": log.changed_by,
                    "reason": log.reason,
                    "created_at": log.created_at.replace(tzinfo=UTC).isoformat(),
                }
                for log in logs
            ]
        )


@router.delete("/api/applications/{app_id}")
async def api_delete_application(app_id: int):
    """Permanently delete an application record."""
    engine = get_engine()
    with Session(engine) as session:
        app = session.query(Application).filter(Application.id == app_id).first()
        if app is None:
            raise HTTPException(status_code=404, detail="Application not found")

        app.deleted_at = datetime.now(UTC)
        session.commit()

        return JSONResponse({"status": "deleted", "application_id": app_id})


@router.patch("/api/applications/{app_id}")
async def api_update_application(app_id: int, data: dict):
    """Update application metadata (outcome, notes, materials path, cover letter)."""
    engine = get_engine()
    with Session(engine) as session:
        app = session.query(Application).filter(Application.id == app_id).first()
        if app is None:
            raise HTTPException(status_code=404, detail="Application not found")

        if app.status in TERMINAL_STATUSES:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot modify a closed application (status: '{app.status}')",
            )

        if "outcome" in data:
            app.outcome = data["outcome"]
        if "outcome_reason" in data:
            app.outcome_reason = data["outcome_reason"]
        if "archived_materials_path" in data:
            app.archived_materials_path = data["archived_materials_path"]
        if "cover_letter" in data:
            app.cover_letter = data["cover_letter"]
        if "interview_stages" in data:
            app.interview_stages = json.dumps(data["interview_stages"])
        if "last_contact_at" in data:
            raw = data["last_contact_at"]
            if raw:
                app.last_contact_at = datetime.fromisoformat(raw)
            else:
                app.last_contact_at = None
        if "follow_up_count" in data:
            app.follow_up_count = int(data["follow_up_count"])
        if "follow_up_notes" in data:
            app.follow_up_notes = data["follow_up_notes"]

        app.updated_at = datetime.now(UTC)
        session.commit()

        return JSONResponse({"status": "ok", "application_id": app.id})


@router.get("/api/applications/follow-up")
async def get_follow_up_applications():
    """Return non-deleted applications needing follow-up (10d+ without contact).

    Soft-deleted rows are excluded, matching ``GET /api/applications``: deleting
    an application leaves its ``status`` untouched, so without this guard a
    deleted application would still be chased for a follow-up.
    """
    engine = get_engine()
    now = datetime.now(UTC)
    with Session(engine) as session:
        ten_days_ago = now - timedelta(days=10)
        query = (
            session.query(Application)
            .options(joinedload(Application.job).joinedload(Job.company_rel))
            .filter(
                Application.status.in_(["applied", "interview", "offer"]),
                Application.deleted_at.is_(None),
            )
            .order_by(Application.updated_at.asc())
        )

        apps = query.all()
        result = []
        for app in apps:
            # Determine last contact time: last_contact_at > updated_at > applied_at
            # SQLite returns these naive; coerce to UTC before comparing with `now`.
            contact_ts = as_utc(app.last_contact_at or app.updated_at or app.applied_at)
            if contact_ts and contact_ts <= ten_days_ago:
                job = app.job
                d = app_to_dict(app)
                d.update(
                    {
                        "job_title": job.title if job else None,
                        "company": job.company_rel.name if job and job.company_rel else None,
                        "days_since_contact": int((now - contact_ts).total_seconds() / 86400),
                    }
                )
                result.append(d)

        return JSONResponse(result)


@router.post("/api/applications/{app_id}/follow-up")
async def record_follow_up(app_id: int, data: dict):
    """Record a follow-up contact on an application.

    Increments ``follow_up_count``, stamps ``last_contact_at`` with now, and
    stores optional free-form notes. This feeds the follow-up tracking signal
    (both the "10d+ since last contact" detection and the per-application count).
    """
    engine = get_engine()
    with Session(engine) as session:
        app = session.query(Application).filter(Application.id == app_id).first()
        if app is None or app.deleted_at is not None:
            raise HTTPException(status_code=404, detail="Application not found")

        if app.status in TERMINAL_STATUSES:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot follow up on a closed application (status: '{app.status}')",
            )

        now = datetime.now(UTC)
        app.follow_up_count = (app.follow_up_count or 0) + 1
        app.last_contact_at = now
        if data.get("notes"):
            app.follow_up_notes = data["notes"]
        app.updated_at = now
        session.commit()

        return JSONResponse(
            {
                "status": "ok",
                "application_id": app.id,
                "follow_up_count": app.follow_up_count,
                "last_contact_at": now.isoformat(),
            }
        )


@router.get("/api/applications/export/csv")
async def export_applications_csv():
    """Export all applications as a CSV file."""
    import csv
    import io

    engine = get_engine()
    with Session(engine) as session:
        query = (
            session.query(Application)
            .options(joinedload(Application.job).joinedload(Job.company_rel))
            .filter(Application.deleted_at.is_(None))
        )
        apps = query.order_by(Application.updated_at.desc()).all()

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(
            [
                "ID",
                "Job Title",
                "Company",
                "Status",
                "Applied At",
                "Interview At",
                "Offer At",
                "Outcome",
                "Outcome Reason",
                "Cover Letter",
                "Follow Up Count",
                "Last Contact At",
                "Archived Materials Path",
            ]
        )
        for app in apps:
            job = app.job
            writer.writerow(
                [
                    app.id,
                    job.title if job else "",
                    job.company_rel.name if job and job.company_rel else "",
                    app.status,
                    app.applied_at.isoformat() if app.applied_at else "",
                    app.interview_at.isoformat() if app.interview_at else "",
                    app.offer_at.isoformat() if app.offer_at else "",
                    app.outcome or "",
                    app.outcome_reason or "",
                    (app.cover_letter or "")[:200] if app.cover_letter else "",
                    app.follow_up_count or 0,
                    app.last_contact_at.isoformat() if app.last_contact_at else "",
                    app.archived_materials_path or "",
                ]
            )

        from fastapi.responses import StreamingResponse as _StreamingResponse

        response = _StreamingResponse(
            iter([output.getvalue()]),
            media_type="text/csv",
            headers={
                "Content-Disposition": "attachment; filename=applications_export.csv",
            },
        )
        return response


@router.post("/api/applications/{app_id}/archive")
async def archive_application(app_id: int, data: dict):
    """Archive application materials and set status to terminal."""
    engine = get_engine()
    with Session(engine) as session:
        app = session.query(Application).filter(Application.id == app_id).first()
        if app is None or app.deleted_at is not None:
            raise HTTPException(status_code=404, detail="Application not found")

        status = data.get("status")
        if status not in TERMINAL_STATUSES:
            raise HTTPException(status_code=400, detail=f"Invalid terminal status: {status}")
        if not _is_valid_transition(app.status, status):
            raise HTTPException(
                status_code=400,
                detail=f"Cannot transition from '{app.status}' to '{status}'",
            )

        archive_dir = _archive_materials(app, status)

        # Update application record
        old_status = app.status
        app.status = status
        app.archived_materials_path = archive_dir
        app.updated_at = datetime.now(UTC)

        # Write application log entry
        log_entry = ApplicationLog(
            application_id=app.id,
            from_status=old_status,
            to_status=status,
            changed_by="user",
        )
        session.add(log_entry)
        session.commit()

        plugin_registry.trigger(
            "on_application_status_change", app_to_dict(app), old_status, status
        )

        return JSONResponse(
            {
                "status": "ok",
                "application_id": app.id,
                "new_status": status,
                "archive_path": archive_dir,
            }
        )


@router.post("/api/applications/{app_id}/prep-pack")
async def generate_prep_pack(app_id: int, data: dict):
    """Generate an interview preparation pack for a specific application and stage.

    Loads the job posting, CV, and cover letter, sends them to the LLM,
    saves the result as ``data/archives/applications/{id}/interview_prep_{stage}.md``,
    and returns the generated content.
    """
    import os as _os

    stage = data.get("stage", "phone_screen")
    allowed_stages = {"phone_screen", "technical", "onsite", "final"}
    if stage not in allowed_stages:
        raise HTTPException(
            status_code=400, detail=f"Invalid stage: {stage}. Choose from {allowed_stages}"
        )

    engine = get_engine()
    with Session(engine) as session:
        app = (
            session.query(Application)
            .options(joinedload(Application.job).joinedload(Job.company_rel))
            .filter(Application.id == app_id)
            .first()
        )
        if app is None or app.deleted_at is not None:
            raise HTTPException(status_code=404, detail="Application not found")

        job = app.job
        if job is None:
            raise HTTPException(status_code=404, detail="Job not found for this application")

        # Collect context
        job_dict = {
            "title": job.title or "",
            "company": job.company_rel.name if job.company_rel else "",
            "description": job.description or "",
            "skills": job.skills_list,
            "category": job.category or "",
            "experience_level": job.experience_level or "",
            "location": job.location or "",
            "salary_min": job.salary_min,
            "salary_max": job.salary_max,
            "currency": job.currency,
        }
        cv_text = ""
        cover_letter_text = app.cover_letter or ""

        # Try to load CV from profile
        try:
            from job_engine.config import ProfileConfig

            pc = ProfileConfig()
            cv_text = pc.load_cv()
        except Exception:
            cv_text = ""

        language = data.get("language")

    # Generate prep pack via LLM
    from job_engine.llm import generate_interview_prep_pack

    prep_pack = generate_interview_prep_pack(
        job=job_dict,
        stage=stage,
        cv_text=cv_text,
        cover_letter_text=cover_letter_text,
        language=language,
    )
    if prep_pack is None:
        raise HTTPException(
            status_code=502,
            detail="Failed to generate prep pack -- LLM unavailable or returned invalid data",
        )

    # Save to archive
    archive_dir = _os.path.join("data", "archives", "applications", str(app.id))
    _os.makedirs(archive_dir, exist_ok=True)
    prep_path = _os.path.join(archive_dir, f"interview_prep_{stage}.md")
    with open(prep_path, "w", encoding="utf-8") as f:
        f.write(f"# Interview Prep Pack -- {stage.replace('_', ' ').title()}\n\n")
        f.write("## Likely Questions\n")
        if isinstance(prep_pack.get("likely_questions"), list):
            for q in prep_pack["likely_questions"]:
                f.write(f"- **{q.get('question', '')}** ({q.get('type', '')})\n")
                f.write(f"  - Prep: {q.get('prep_tip', '')}\n")
                if q.get("star"):
                    star = q["star"]
                    f.write(
                        f"  - STAR: {star.get('situation', '')} -> {star.get('task', '')} -> "
                        f"{star.get('action', '')} -> {star.get('result', '')}\n"
                    )
                f.write("\n")
        f.write("\n## STAR Mapping\n")
        if isinstance(prep_pack.get("star_mapping"), list):
            for sm in prep_pack["star_mapping"]:
                f.write(f"- **{sm.get('category', '')}**: {sm.get('story_angle', '')}\n")
                f.write(f"  - Skill: {sm.get('relevant_skill', '')}\n")
                f.write(f"  - Experience: {sm.get('suggested_experience', '')}\n\n")
        f.write("\n## Company Research\n")
        cr = prep_pack.get("company_research", {})
        if isinstance(cr, dict):
            f.write(f"{cr.get('brief', '')}\n\n")
            f.write("### Key Topics\n")
            for topic in cr.get("key_topics", []):
                f.write(f"- {topic}\n")
            f.write("\n### Questions to Ask\n")
            for qa in cr.get("questions_to_ask", []):
                f.write(f"- {qa}\n")
        f.write("\n## Consistency Brief\n")
        cb = prep_pack.get("consistency_brief", {})
        if isinstance(cb, dict):
            f.write(f"**Narrative arc**: {cb.get('narrative_arc', '')}\n\n")
            f.write("### CV Highlights\n")
            for h in cb.get("cv_highlights", []):
                f.write(f"- {h}\n")
            f.write("\n### Cover Letter Themes\n")
            for t in cb.get("cover_letter_themes", []):
                f.write(f"- {t}\n")

    return JSONResponse(
        {
            "status": "ok",
            "application_id": app_id,
            "stage": stage,
            "prep_pack": prep_pack,
            "prep_path": prep_path,
        }
    )


@router.post("/api/applications/{app_id}/generate-cv")
async def generate_cv_for_application(app_id: int):
    """Generate a job-tailored CV PDF for this application.

    Uses the CV Drafter Agent to produce a moderncv LaTeX document
    tailored to the job posting, compiles it with tectonic, verifies
    it (2 pages, ATS), and saves it to the application archive.
    """
    engine = get_engine()
    with Session(engine) as session:
        app = (
            session.query(Application)
            .options(joinedload(Application.job).joinedload(Job.company_rel))
            .filter(Application.id == app_id)
            .first()
        )
        if app is None or app.deleted_at is not None:
            raise HTTPException(status_code=404, detail="Application not found")

        job = app.job
        if job is None:
            raise HTTPException(status_code=404, detail="Job not found for this application")

        # Build job dict matching llm.py expectations
        job_dict = {
            "title": job.title or "",
            "company": job.company_rel.name if job.company_rel else "",
            "description": job.description or "",
            "skills": job.skills_list,
            "category": job.category or "",
            "experience_level": job.experience_level or "",
            "location": job.location or "",
            "salary_min": job.salary_min,
            "salary_max": job.salary_max,
            "currency": job.currency,
            "remote": job.remote or False,
            "contract_type": job.contract_type or "",
        }

        # Load profile config
        from job_engine.config import ProfileConfig

        profile_config = ProfileConfig()
        profile = profile_config.load()

    # Generate CV via LLM drafter
    from job_engine.llm import generate_cv

    cv_result = generate_cv(job=job_dict, profile=profile)
    if cv_result is None:
        raise HTTPException(status_code=502, detail="Failed to generate CV — LLM unavailable")
    if not cv_result.get("cv_latex"):
        raise HTTPException(status_code=502, detail="CV drafter returned empty LaTeX")

    # Compile with tectonic
    from job_engine.latex_compiler import LatexError, ats_verify_pdf, compile_latex, verify_cv

    archive_dir = os.path.join("data", "archives", "applications", str(app_id))
    job_keywords = job_dict.get("skills", [])
    if isinstance(job_keywords, str):
        job_keywords = [job_keywords]
    try:
        pdf_path = compile_latex(
            tex_content=cv_result["cv_latex"],
            output_dir=archive_dir,
            name="cv",
        )
        verification = verify_cv(pdf_path)
        ats_result = ats_verify_pdf(pdf_path, job_keywords)
    except LatexError as exc:
        logger.warning("CV PDF build failed for application %d: %s", app_id, exc)
        raise HTTPException(status_code=502, detail=f"CV compilation failed: {exc}") from exc

    return JSONResponse(
        {
            "status": "ok",
            "application_id": app_id,
            "pdf_path": pdf_path,
            "cv_latex_path": os.path.join(archive_dir, "cv.tex"),
            "skills_covered": cv_result.get("skills_covered", []),
            "skills_gapped": cv_result.get("skills_gapped", []),
            "nice_to_haves_engaged": cv_result.get("nice_to_haves_engaged", []),
            "summary": cv_result.get("summary", ""),
            "verification": verification,
            "ats": ats_result,
        }
    )


@router.post("/api/applications/{app_id}/generate-cover-letter-pdf")
async def generate_cover_letter_pdf(app_id: int):
    """Wrap the existing cover letter text into a professional PDF.

    Uses the existing cover letter text stored on the application,
    wraps it in a LaTeX template, compiles with tectonic, and saves.
    """
    engine = get_engine()
    with Session(engine) as session:
        app = (
            session.query(Application)
            .options(joinedload(Application.job).joinedload(Job.company_rel))
            .filter(Application.id == app_id)
            .first()
        )
        if app is None or app.deleted_at is not None:
            raise HTTPException(status_code=404, detail="Application not found")

        job = app.job
        if job is None:
            raise HTTPException(status_code=404, detail="Job not found")

        if not app.cover_letter:
            raise HTTPException(
                status_code=400,
                detail="No cover letter text on this application — generate one first",
            )

        # Load profile for sender info
        from job_engine.config import ProfileConfig

        profile = ProfileConfig().load()
        first_name = (profile.get("name", "") or "").split(" ", 1)[0] if profile.get("name") else ""
        last_name = (
            (profile.get("name", "") or "").split(" ", 1)[-1]
            if profile.get("name") and " " in (profile.get("name", "") or "")
            else ""
        )
        email = profile.get("email", "") or ""
        phone = profile.get("phone", "") or ""
        company_name = job.company_rel.name if job.company_rel else ""

    # Wrap and compile
    from job_engine.cover_letter_pdf import wrap_cover_letter
    from job_engine.latex_compiler import LatexError, ats_verify_pdf, verify_cover_letter

    archive_dir = os.path.join("data", "archives", "applications", str(app_id))
    job_keywords = job.skills_list if job else []
    try:
        pdf_path = wrap_cover_letter(
            letter_text=app.cover_letter,
            output_dir=archive_dir,
            name="cover_letter",
            first_name=first_name,
            last_name=last_name,
            email=email,
            phone=phone,
            company=company_name,
        )
        verification = verify_cover_letter(pdf_path)
        ats_result = ats_verify_pdf(pdf_path, job_keywords)
    except LatexError as exc:
        logger.warning("Cover letter PDF build failed for application %d: %s", app_id, exc)
        raise HTTPException(
            status_code=502, detail=f"Cover letter PDF compilation failed: {exc}"
        ) from exc

    return JSONResponse(
        {
            "status": "ok",
            "application_id": app_id,
            "pdf_path": pdf_path,
            "tex_path": os.path.join(archive_dir, "cover_letter.tex"),
            "verification": verification,
            "ats": ats_result,
        }
    )


@router.get("/api/applications/{app_id}/files/{filename:path}")
async def download_application_file(app_id: int, filename: str):
    """Serve a file from the application's archive directory."""
    from fastapi.responses import FileResponse

    allowed_dir = Path("data", "archives", "applications", str(app_id)).resolve()
    file_path = (allowed_dir / filename).resolve()
    # Security: prevent path traversal (incl. sibling dirs like "1" vs "12")
    if not file_path.is_relative_to(allowed_dir):
        raise HTTPException(status_code=403, detail="Access denied")

    if not os.path.isfile(file_path):
        raise HTTPException(status_code=404, detail="File not found")

    return FileResponse(file_path)
