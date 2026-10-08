"""Shared helper functions extracted from route modules to reduce duplication.

Provides session management, common lookups, serialization helpers,
and reusable stats computation for all dashboard routes.
"""

from __future__ import annotations

import json
import logging
from collections import Counter
from datetime import UTC, datetime
from typing import Any

from job_engine.database import get_sync_engine as get_engine
from job_engine.models import Job
from job_engine.skill_gap import analyze_skill_gaps
from sqlalchemy.orm import Session

from dashboard.common import load_profile

logger = logging.getLogger(__name__)

# ── Session & Lookups ─────────────────────────────────────────────────────────


def get_session() -> Session:
    """Get a synchronous DB session."""
    return Session(get_engine())


def get_job_or_404(session: Session, job_id: str) -> Job:
    """Look up a job by external_id, raise 404 if not found."""
    job = session.query(Job).filter(Job.external_id == job_id).first()
    if not job:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Job not found")
    return job


def toggle_job_field(session: Session, job_id: str, field: str) -> bool:
    """Generic toggle for a boolean Job field (hidden, favorite). Returns new value."""
    job = get_job_or_404(session, job_id)
    current = getattr(job, field, False)
    new_val = not current
    setattr(job, field, new_val)
    setattr(job, "updated_at", datetime.now(UTC))
    session.commit()
    return new_val


# ── Serialization ─────────────────────────────────────────────────────────────


def app_to_dict(app) -> dict:
    """Serialize an Application ORM instance to a plain dict."""
    return {
        "id": app.id,
        "job_id": app.job_id,
        "job_external_id": app.job.external_id if app.job else None,
        "status": app.status,
        "outcome": app.outcome,
        "outcome_reason": app.outcome_reason,
        "cover_letter": app.cover_letter,
        "archived_materials_path": app.archived_materials_path,
        "interview_stages": json.loads(app.interview_stages) if app.interview_stages else {},
        "last_contact_at": app.last_contact_at.isoformat() if app.last_contact_at else None,
        "follow_up_count": app.follow_up_count,
        "follow_up_notes": app.follow_up_notes,
        "applied_at": app.applied_at.isoformat() if app.applied_at else None,
        "created_at": app.created_at.isoformat() if app.created_at else None,
        "updated_at": app.updated_at.isoformat() if app.updated_at else None,
    }


# ── Dashboard Stats ───────────────────────────────────────────────────────────


def _pct(count: int, total: int) -> int:
    """Return count as a whole-number percentage of total (0 when total is 0)."""
    return round(count / max(total, 1) * 100)


def compute_dashboard_stats(
    visible_jobs: list[dict],
) -> dict[str, Any]:
    """Compute dashboard statistics from a filtered list of job dicts.

    Returns a dict with keys matching the context expected by the overview API
    endpoint (``/api/dashboard/stats``).
    """
    now = datetime.now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    # ── Basic stats ──────────────────────────────────────────────────────────
    total_jobs = len(visible_jobs)
    avg_score = round(sum(j.get("match_score", 0) for j in visible_jobs) / max(total_jobs, 1), 1)
    high_match_count = sum(1 for j in visible_jobs if j.get("match_score", 0) >= 50)
    platform_count = len(set(j.get("platform", "") for j in visible_jobs))

    # New jobs discovered today
    new_today = 0
    for j in visible_jobs:
        raw = j.get("discovered_at") or ""
        try:
            dt = datetime.fromisoformat(raw) if raw else None
        except (ValueError, TypeError):
            dt = None
        if dt and dt >= today_start:
            new_today += 1

    # Best match
    best_match = max(
        (j for j in visible_jobs if j.get("match_score") is not None),
        key=lambda j: j["match_score"],
        default=None,
    )
    best_match_score = best_match["match_score"] if best_match else 0

    # ── Top 5 matches ────────────────────────────────────────────────────────
    top_matches = sorted(visible_jobs, key=lambda j: j.get("match_score", 0), reverse=True)[:5]

    # ── 5 newest jobs ────────────────────────────────────────────────────────
    newest_jobs = sorted(
        (j for j in visible_jobs if j.get("discovered_at")),
        key=lambda j: j["discovered_at"],
        reverse=True,
    )[:5]

    # ── AI Insights — most recently analyzed jobs ────────────────────────────
    llm_jobs = [j for j in visible_jobs if j.get("llm_analysis")]
    recent_llm_jobs = sorted(llm_jobs, key=lambda j: j.get("updated_at") or "", reverse=True)[:3]

    # ── Match score distribution ────────────────────────────────────────────
    match_dist_buckets = [
        sum(1 for j in visible_jobs if j.get("match_score", 0) < 25),
        sum(1 for j in visible_jobs if 25 <= j.get("match_score", 0) < 50),
        sum(1 for j in visible_jobs if 50 <= j.get("match_score", 0) < 75),
        sum(1 for j in visible_jobs if j.get("match_score", 0) >= 75),
    ]

    # ── Top skills (market frequency, no limit) ─────────────────────────────
    skill_counts: dict[str, dict[str, int | str]] = {}
    for j in visible_jobs:
        skills = j.get("skills", [])
        if isinstance(skills, list):
            for s in skills:
                key = s.lower().strip()
                if key not in skill_counts:
                    skill_counts[key] = {"name": s.strip(), "count": 0}
                skill_counts[key]["count"] += 1  # type: ignore[operator]
    top_skills = sorted(skill_counts.values(), key=lambda x: x["count"], reverse=True)
    top_skills = [(s["name"], s["count"]) for s in top_skills]

    # ── Profile skills count (for the badge — total in user's profile) ─────
    profile = load_profile()
    profile_skills_count = 0
    if profile:
        for category, skill_list in profile.get("skills", {}).items():
            if isinstance(skill_list, list):
                profile_skills_count += len(skill_list)

    # ── Platform counts ─────────────────────────────────────────────────────
    platform_counts: Counter[str] = Counter()
    for j in visible_jobs:
        platform_counts[j.get("platform", "unknown")] += 1
    top_platforms = platform_counts.most_common()

    # ── Work mode percentages ───────────────────────────────────────────────
    remote_count = 0
    hybrid_count = 0
    for j in visible_jobs:
        loc = (j.get("location") or "").lower()
        if j.get("remote") or "remote" in loc:
            remote_count += 1
        elif "hybrid" in loc:
            hybrid_count += 1
    remote_pct = _pct(remote_count, total_jobs)
    hybrid_pct = _pct(hybrid_count, total_jobs)
    office_pct = 100 - remote_pct - hybrid_pct  # guarantees 100% total

    # ── Critical skill gaps ───────────────────────────────────────────────
    critical_gaps: list[dict[str, Any]] = []
    try:
        profile = load_profile()
        report = analyze_skill_gaps(visible_jobs, profile)
        for g in report.gaps:
            if g.priority == "Critical" and not g.in_profile:
                critical_gaps.append(
                    {
                        "name": g.skill,
                        "frequency": g.frequency,
                        "priority": g.priority,
                    }
                )
                if len(critical_gaps) >= 5:
                    break
    except Exception:
        logger.warning("Failed to compute critical skill gaps", exc_info=True)

    # ── Per-dimension score averages ────────────────────────────────────────
    dimension_scores: dict[str, float] = {}
    dim_counts: dict[str, int] = {}
    for j in visible_jobs:
        comps = j.get("match_details", {}).get("components", {})
        if not comps:
            continue
        for key, info in comps.items():
            if isinstance(info, dict) and "score" in info:
                score = info["score"]
                if isinstance(score, (int, float)):
                    dimension_scores[key] = dimension_scores.get(key, 0) + score
                    dim_counts[key] = dim_counts.get(key, 0) + 1
    avg_dimensions = {
        key: round(dimension_scores[key] / dim_counts[key], 1) for key in dimension_scores
    }

    # ── Salary snapshot ────────────────────────────────────────────────────
    jobs_with_salary = sum(1 for j in visible_jobs if j.get("salary_min") or j.get("salary_max"))
    salary_coverage_pct = _pct(jobs_with_salary, total_jobs)

    # ── Contract type distribution ─────────────────────────────────────────
    contract_counts: Counter[str] = Counter()
    for j in visible_jobs:
        ct = j.get("contract_type", "").lower()
        if ct:
            contract_counts[ct] += 1
    top_contracts = contract_counts.most_common()

    # ── Application stats ──────────────────────────────────────────────────
    application_funnel = {
        "applied": sum(1 for j in visible_jobs if j.get("application_id") is not None),
        "interview": sum(1 for j in visible_jobs if j.get("application_status") == "interview"),
        "offer": sum(1 for j in visible_jobs if j.get("application_status") == "offer"),
    }

    # ── LLM coverage ───────────────────────────────────────────────────────
    llm_count = sum(
        1
        for j in visible_jobs
        if j.get("llm_analysis") and j["llm_analysis"] not in ("", "{}", "null")
    )

    return {
        "total_jobs": total_jobs,
        "avg_score": avg_score,
        "high_match_count": high_match_count,
        "platform_count": platform_count,
        "new_today": new_today,
        "best_match_score": best_match_score,
        "top_matches": top_matches,
        "newest_jobs": newest_jobs,
        "recent_llm_jobs": recent_llm_jobs,
        "match_dist_buckets": match_dist_buckets,
        "top_skills": top_skills,
        "profile_skills_count": profile_skills_count,
        "top_platforms": top_platforms,
        "remote_pct": remote_pct,
        "hybrid_pct": hybrid_pct,
        "office_pct": office_pct,
        "critical_gaps": critical_gaps,
        "avg_dimensions": avg_dimensions,
        "salary_coverage_pct": salary_coverage_pct,
        "jobs_with_salary": jobs_with_salary,
        "top_contracts": top_contracts,
        "application_funnel": application_funnel,
        "llm_count": llm_count,
    }
