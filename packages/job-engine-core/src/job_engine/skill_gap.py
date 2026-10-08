"""
Skill Gap Analysis — identifies learning opportunities from market demand.

Workflow:
  1. Load all scored jobs from the DB
  2. Build a frequency map of skills mentioned across all job listings
  3. Cross-reference against the candidate's profile skills
  4. Produce a fit-weighted gap heatmap and learning plan

Usage:
  from job_engine.skill_gap import analyze_skill_gaps, SkillGapReport
  report = analyze_skill_gaps(jobs, profile)
  print(report.gaps)  # list of SkillGap namedtuples
"""

import json
import logging
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Any

from job_engine.taxonomy import (
    TaxonomyResolver,
)

logger = logging.getLogger(__name__)


# ── Data types ──────────────────────────────────────────────────────────


@dataclass
class SkillGap:
    """A single skill gap detected in the market."""

    skill: str
    frequency: int  # number of job listings mentioning this skill
    avg_match_score: float  # average match score of jobs mentioning this skill
    in_profile: bool  # whether the candidate already has this skill
    priority: str = ""  # filled by priority_assignment: Critical/High/Medium/Low


@dataclass
class SkillGapReport:
    """Complete skill gap analysis report."""

    gaps: list[SkillGap] = field(default_factory=list)
    total_jobs: int = 0
    scanned_skills: int = 0
    profile_skills: list[str] = field(default_factory=list)
    market_skills: list[str] = field(default_factory=list)
    since_last: str = ""  # diff notes from previous analysis


# ── Constants ───────────────────────────────────────────────────────────


# Default resolver instance (lazy-init, no DB session — in-memory only)
_resolver: TaxonomyResolver | None = None


def _get_resolver() -> TaxonomyResolver:
    global _resolver
    if _resolver is None:
        _resolver = TaxonomyResolver()
    return _resolver


# ── Analysis ────────────────────────────────────────────────────────────


def _normalize_skill(skill: str) -> str:
    """Normalize a skill name to its canonical taxonomy slug.

    Replaces the old _DEFAULT_SKILL_CLUSTERS approach.  Uses the taxonomy
    resolver's built-in alias map for canonicalization.  If the skill is
    unknown, returns the canonicalized variant form (lowercase, underscores).
    """
    return _get_resolver().resolve(skill, "skill")


def analyze_skill_gaps(
    jobs: list[dict[str, Any]],
    profile: dict[str, Any] | None = None,
) -> SkillGapReport:
    """Analyze skill gaps between the candidate's profile and market demand.

    Args:
        jobs: List of scored job dicts (any match score helps weight results).
        profile: The candidate's profile dict (skills, etc.).

    Returns:
        A SkillGapReport with sorted gap entries.
    """
    # Extract candidate profile skills, resolved via taxonomy
    candidate_skills: set[str] = set()
    if profile:
        for category, skill_list in profile.get("skills", {}).items():
            if isinstance(skill_list, list):
                for s in skill_list:
                    candidate_skills.add(_normalize_skill(s))

    resolver = _get_resolver()

    # Build market skill frequency map
    skill_freq: dict[str, dict[str, Any]] = defaultdict(lambda: {"count": 0, "total_score": 0.0})
    # Track one original spelling per normalized skill for display
    skill_originals: dict[str, str] = {}

    for job in jobs:
        job_skills = job.get("skills", [])
        if isinstance(job_skills, str):
            try:
                job_skills = json.loads(job_skills)
            except (json.JSONDecodeError, TypeError):
                job_skills = []

        match_score = job.get("match_score", 50.0) or 50.0

        # Track raw skills from the job listing
        seen_skills: set[str] = set()
        for s in job_skills:
            normalized = _normalize_skill(s)
            seen_skills.add(normalized)
            # Record the first original spelling encountered for display
            if normalized not in skill_originals:
                skill_originals[normalized] = s.strip()

        for skill in seen_skills:
            skill_freq[skill]["count"] += 1
            skill_freq[skill]["total_score"] += match_score

    total_jobs = max(len(jobs), 1)

    # Build gap entries
    gaps: list[SkillGap] = []
    for skill, data in skill_freq.items():
        # Prefer the listing's original spelling only when it has distinctive
        # casing (e.g. "PyTorch"); otherwise use the canonical taxonomy label.
        original = skill_originals.get(skill, "")
        display_name = (
            original if original and original != original.lower() else resolver.get_label(skill)
        )
        gaps.append(
            SkillGap(
                skill=display_name,
                frequency=data["count"],
                avg_match_score=round(data["total_score"] / max(data["count"], 1), 1),
                in_profile=skill in candidate_skills,
            )
        )

    # Sort by frequency descending (most in-demand first)
    gaps.sort(key=lambda g: g.frequency, reverse=True)

    # Assign priority based on frequency × match_score × !in_profile
    for gap in gaps:
        if gap.in_profile:
            gap.priority = "Low"  # already known — just confirmation
        elif gap.frequency >= max(int(total_jobs * 0.1), 5):
            gap.priority = "Critical"
        elif gap.frequency >= max(int(total_jobs * 0.05), 3):
            gap.priority = "High"
        elif gap.frequency >= 2:
            gap.priority = "Medium"
        else:
            gap.priority = "Low"

    # Filter out zero-frequency entries
    gaps = [g for g in gaps if g.frequency > 0]

    report = SkillGapReport(
        gaps=gaps,
        total_jobs=total_jobs,
        scanned_skills=len(skill_freq),
        profile_skills=sorted(candidate_skills),
        market_skills=sorted(skill_freq.keys()),
        since_last="",
    )

    return report


# ── Summary helpers ─────────────────────────────────────────────────────


def format_gap_summary(report: SkillGapReport) -> dict[str, Any]:
    """Return a summary dict for API responses."""
    counts = Counter(g.priority for g in report.gaps)

    # Top skills to learn (not in profile, high frequency)
    to_learn = [
        {"skill": g.skill, "frequency": g.frequency, "priority": g.priority}
        for g in report.gaps
        if not g.in_profile and g.priority in ("Critical", "High")
    ]

    return {
        "total_jobs_scanned": report.total_jobs,
        "total_market_skills": report.scanned_skills,
        "profile_skills_count": len(report.profile_skills),
        "critical_gaps": counts.get("Critical", 0),
        "high_gaps": counts.get("High", 0),
        "medium_gaps": counts.get("Medium", 0),
        "low_gaps": counts.get("Low", 0),
        "skills_to_learn": to_learn,
        "all_gaps": [
            {
                "skill": g.skill,
                "frequency": g.frequency,
                "avg_match_score": g.avg_match_score,
                "in_profile": g.in_profile,
                "priority": g.priority,
            }
            for g in report.gaps  # all gaps
        ],
    }
