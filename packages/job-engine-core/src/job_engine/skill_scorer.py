import json
import logging
import sys
from pathlib import Path
from typing import Any

from job_engine.config import ProfileConfig
from job_engine.currency_converter import convert
from job_engine.taxonomy import (
    TaxonomyResolver,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Shared skill normalizer — mirrors the JS normalizeSkills() in core/skills.js
# Keep only [a-z] and whitespace (single spaces). Underscores are converted
# to spaces first so `machine_learning` → `machine learning`.
# This ensures consistent normalization across scraping (JS) and scoring (Python).
# ---------------------------------------------------------------------------


def normalize_skill(skill: str) -> str:
    """Normalize a single skill name: keep only letter characters, digits,
    and whitespace — everything else is replaced with a space.
    Underscores are converted to spaces first so that `machine_learning` →
    `machine learning`. Dots are also replaced with spaces so that `kat. b`
    and `kat b` collapse to the same normalized form. Collapses whitespace
    and preserves Unicode letters (a-z, ł, ś, ć, etc.) and numbers (0-9).

    Mirrors the JS normalizeSkill() in packages/job-engine-scrapers/core/skills.js.
    """
    s = skill.lower().strip()
    s = s.replace("_", " ")  # underscores → spaces first
    # Replace non-letters, non-digits, non-spaces with a space
    s = "".join(c if c.isalpha() or c.isdigit() or c.isspace() else " " for c in s)
    s = " ".join(s.split())  # collapse whitespace
    return s


def normalize_skills(skills: list[str]) -> list[str]:
    """Normalize a list of skill names, deduplicate, and filter empty results.

    Mirrors the JS normalizeSkills() in packages/job-engine-scrapers/core/skills.js.
    """
    if not skills:
        return []
    seen: set[str] = set()
    result: list[str] = []
    for s in skills:
        if not isinstance(s, str) or not s.strip():
            continue
        normalized = normalize_skill(s)
        if normalized and normalized not in seen:
            seen.add(normalized)
            result.append(normalized)
    return result


# ---------------------------------------------------------------------------
# Profile loader — delegates to ProfileConfig singleton
# ---------------------------------------------------------------------------


def load_profile(path: str = "data/my_profile.yaml") -> dict[str, Any]:
    """Load and parse the YAML profile via ProfileConfig (single source of truth)."""
    return ProfileConfig(yaml_path=Path(path)).load()


# ---------------------------------------------------------------------------
# Weight configuration
# ---------------------------------------------------------------------------

# Base weights for each scoring dimension (must sum to 1.0)
WEIGHTS = {
    "skill_overlap": 0.25,  # 25% — how many of our skills appear in the job
    "keyword_boost": 0.15,  # 15% — domain keywords (trading, fintech, etc.)
    "location_fit": 0.08,  #  8% — remote / city / hybrid match vs preferences
    "rate_fit": 0.12,  # 12% — salary range vs expected rate (configurable currency)
    "category_fit": 0.08,  #  8% — job category aligns with profile skill categories
    "experience_fit": 0.04,  #  4% — seniority level match
    "behavioral_fit": 0.13,  # 13% — culture, collaboration, growth keywords
    "career_alignment": 0.15,  # 15% — long-term career trajectory, domain interest
}

# Human-readable labels for UI display
DIMENSION_LABELS = {
    "skill_overlap": "Skill Overlap",
    "keyword_boost": "Keyword Boost",
    "location_fit": "Location Fit",
    "rate_fit": "Rate Fit",
    "category_fit": "Category Fit",
    "experience_fit": "Experience Fit",
    "behavioral_fit": "Behavioral Fit",
    "career_alignment": "Career Alignment",
}

# ── Scoring constants ────────────────────────────────────────────────

# Critical skill bonus: +5 points per critical skill match, capped at 20
CRITICAL_BONUS_PER_MATCH = 5
CRITICAL_BONUS_CAP = 20

# Currency assumed when neither the job nor the profile specifies one.
DEFAULT_CURRENCY = "USD"

# Field values that mean "no usable data" (treated as neutral when scoring).
NO_DATA_VALUES = {"n/a", "?"}


def resolve_currency(*candidates: Any) -> str:
    """Return the first truthy currency candidate uppercased, else DEFAULT_CURRENCY."""
    for candidate in candidates:
        if candidate:
            return str(candidate).upper()
    return DEFAULT_CURRENCY


# ---------------------------------------------------------------------------
# Matcher
# ---------------------------------------------------------------------------


class JobMatcher:
    """Scores job listings against a profile."""

    def __init__(
        self,
        profile_path: str = "data/my_profile.yaml",
        taxonomy_resolver: TaxonomyResolver | None = None,
    ):
        self.profile = load_profile(profile_path)
        self.taxonomy = taxonomy_resolver or TaxonomyResolver()
        self._build_skill_index()
        # Keyword sets: raw profile values → lowercased → canonical slugs.
        self.boosted_keywords = self._resolve_keyword_set(
            self.profile.get("boosted_keywords", []), "boosted"
        )
        self.behavioral_keywords = self._resolve_keyword_set(
            self._flatten_values(self.profile.get("behavioral_keywords", {})), "behavioral"
        )
        self.career_keywords = self._resolve_keyword_set(
            self._flatten_values(self.profile.get("career_goals", {})), "career"
        )

        self.excluded_companies = [c.lower() for c in self.profile.get("excluded_companies", [])]

    def _build_skill_index(self) -> None:
        """Flatten all skills into a single set with category tags, resolved via taxonomy."""
        skills = self.profile.get("skills", {})
        self.all_skills: dict[str, str] = {}  # slug -> category
        self.critical_skills: set[str] = set()  # slugs from critical categories

        # Read which categories get the critical bonus
        critical_cats = set(
            cat.lower().strip()
            for cat in self.profile.get("critical_categories", [])
            if isinstance(cat, str)
        )

        for category, skill_list in skills.items():
            cat_lower = category.lower().strip()
            for skill in skill_list:
                # Resolve via taxonomy to get canonical slug
                slug = self.taxonomy.resolve(skill, "skill")
                if not slug:
                    continue
                self.all_skills[slug] = cat_lower
                if cat_lower in critical_cats:
                    self.critical_skills.add(slug)

    @staticmethod
    def _flatten_values(data: Any) -> list[str]:
        """Flatten a profile field into a flat list of strings.

        Accepts either the new flat-list format or the legacy dict-of-lists
        format (values concatenated); anything else yields an empty list.
        """
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            values: list[str] = []
            for items in data.values():
                if isinstance(items, list):
                    values.extend(items)
            return values
        return []

    def _resolve_keyword_set(self, values: list[str], kind: str) -> set[str]:
        """Lowercase/strip raw keyword values and resolve each to its canonical slug."""
        normalized = {kw.lower().strip() for kw in values}
        return {self.taxonomy.resolve(kw, kind) or kw for kw in normalized}

    # ---- scoring methods ----

    def score(self, job: dict[str, Any]) -> float:
        """Return a match score 0-100 for a job dict."""
        details = self.score_detail(job)
        return details["total_score"]

    def score_detail(self, job: dict[str, Any]) -> dict[str, Any]:
        """Return a detailed score breakdown."""
        # Check exclusions first
        company = (job.get("company") or "").lower()
        if company in self.excluded_companies:
            return {
                "total_score": 0.0,
                "reason": f"Excluded company: {job.get('company')}",
                "components": {},
            }

        components = {}

        # Scoring dimensions — each maps to a _score_* method on self
        scoring_dimensions = [
            ("skill_overlap", "_score_skills"),
            ("keyword_boost", "_score_keywords"),
            ("location_fit", "_score_location"),
            ("rate_fit", "_score_rate"),
            ("category_fit", "_score_category"),
            ("experience_fit", "_score_experience"),
            ("behavioral_fit", "_score_behavioral"),
            ("career_alignment", "_score_career"),
        ]

        for key, method_name in scoring_dimensions:
            score_value = getattr(self, method_name)(job)
            components[key] = {
                "score": score_value,
                "weight": WEIGHTS[key],
                "label": DIMENSION_LABELS.get(key, key.replace("_", " ").title()),
            }

        # Weighted sum, normalized to 0-100
        total = sum(comp["score"] * comp["weight"] for comp in components.values())
        total = round(min(total, 100.0), 1)

        job_slugs_set = self._job_skill_slugs(job)
        return {
            "total_score": total,
            "reason": "ok",
            "components": components,
            "skill_gap": {
                "matched": sorted(job_slugs_set & self.all_skills.keys()),
                "missing": sorted(job_slugs_set - self.all_skills.keys()),
            },
        }

    def _job_skill_slugs(self, job: dict[str, Any]) -> set[str]:
        """Return the job's skills as canonical taxonomy slugs."""
        # Prefer pre-resolved slugs from database, fall back to raw skills
        job_slugs = job.get("skills_slugs")
        if job_slugs and isinstance(job_slugs, list):
            return {s.lower().strip() for s in job_slugs if s}
        job_slugs_set = set()
        for s in self._get_job_skills(job):
            slug = self.taxonomy.resolve(s, "skill")
            if slug:
                job_slugs_set.add(slug)
        return job_slugs_set

    def _score_skills(self, job: dict[str, Any]) -> float:
        """Score based on skill overlap using canonical taxonomy slugs."""
        job_slugs_set = self._job_skill_slugs(job)

        if not job_slugs_set or not self.all_skills:
            return 0.0

        matched = [slug for slug in job_slugs_set if slug in self.all_skills]

        # Score = percentage of job's required skills matched by profile
        denominator = max(len(job_slugs_set), 1)
        raw = (len(matched) / denominator) * 100

        # Bonus for critical skill matches (from critical_categories in profile)
        critical_matches = sum(1 for s in matched if s in self.critical_skills)
        critical_bonus = min(critical_matches * CRITICAL_BONUS_PER_MATCH, CRITICAL_BONUS_CAP)

        return min(raw + critical_bonus, 100.0)

    def _count_keyword_hits(self, job: dict[str, Any], keywords: set[str]) -> int:
        """Count how many keyword slugs appear in the job text (variant-aware)."""
        text = self._get_job_text(job).lower()
        return sum(
            1
            for slug in keywords
            if any(st in text for st in self.taxonomy.canonicalize_for_text_search(slug))
        )

    def _score_keywords(self, job: dict[str, Any]) -> float:
        """Score based on boosted keyword presence using variant-aware text search."""
        if not self.boosted_keywords:
            return 0.0
        # Score = (found / total_boosted) * 100, cap at 100
        found = self._count_keyword_hits(job, self.boosted_keywords)
        return min((found / len(self.boosted_keywords)) * 100, 100.0)

    def _score_location(self, job: dict[str, Any]) -> float:
        """Score based on location/remote fit vs profile preferences."""
        remote_only = self.profile.get("remote_only", False)
        preferred_locs = [
            loc.lower().strip() for loc in self.profile.get("preferred_locations", [])
        ]

        job_location = (job.get("location") or "").lower().strip()
        job_city = (job.get("city") or "").lower().strip()
        job_remote = job.get("remote", False)

        # If profile says remote_only and job is remote → perfect
        if remote_only and job_remote:
            return 100.0

        # If job location/city is in preferred locations → perfect
        if job_location in preferred_locs or job_city in preferred_locs:
            return 100.0

        # If remote_only is not set but job is remote → good (70)
        if job_remote:
            return 70.0

        # If remote_only is true but job is not remote and not in preferred → 0
        if remote_only:
            return 0.0

        # Default: neutral
        return 50.0

    def _score_rate(self, job: dict[str, Any]) -> float:
        """Score based on salary fit vs expected rate.

        Compares job salary against profile expectations.  If currencies
        differ, converts via the ``currency_converter`` module (auto-refreshed
        daily from open.er-api.com).  Falls back to the profile's optional
        ``exchange_rates`` section (e.g. ``{EUR: 1.0, USD: 1.1, PLN: 4.3}``)
        only if the auto-converter is unavailable.
        """
        profile_rate = self.profile.get("rate", {})
        profile_currency = resolve_currency(
            profile_rate.get("currency"), self.profile.get("currency")
        )
        profile_min = profile_rate.get("min_monthly")
        profile_max = profile_rate.get("max_monthly")

        job_min = job.get("salary_min")
        job_max = job.get("salary_max")
        job_currency = resolve_currency(job.get("currency"))

        # If job has no salary data → neutral (don't penalise)
        if job_min is None and job_max is None:
            return 50.0

        # Default min/max if one side is missing
        if job_min is None:
            job_min = job_max
        if job_max is None:
            job_max = job_min

        # Both are guaranteed non-None here (the both-None case returned above).
        assert job_min is not None and job_max is not None
        job_min = float(job_min)
        job_max = float(job_max)

        if job_min > job_max:
            job_min, job_max = job_max, job_min

        # Currency conversion: try the auto-updating converter first,
        # then fall back to the profile's static exchange_rates.
        if job_currency != profile_currency:
            converted_min = convert(job_min, job_currency, profile_currency)
            converted_max = convert(job_max, job_currency, profile_currency)
            if converted_min is not None and converted_max is not None:
                job_min = converted_min
                job_max = converted_max
            else:
                # Fallback: profile's static exchange_rates
                exchange_rates = self.profile.get("exchange_rates", {})
                if exchange_rates:
                    job_to_usd = exchange_rates.get(job_currency)
                    profile_to_usd = exchange_rates.get(profile_currency)
                    if job_to_usd and profile_to_usd:
                        job_min = job_min / job_to_usd * profile_to_usd
                        job_max = job_max / job_to_usd * profile_to_usd

        # If no profile rate expectations → neutral
        if profile_min is None or profile_max is None:
            return 50.0

        profile_min = float(profile_min)
        profile_max = float(profile_max)

        # Job is fully below profile minimum → underpaid
        if job_max < profile_min:
            ratio = job_max / max(profile_min, 1)
            return round(ratio * 50, 1)  # 0-50 proportional

        # Job is fully above profile maximum → opportunity, score 80
        if job_min > profile_max:
            return 80.0

        # Calculate overlap percentage
        overlap_min = max(job_min, profile_min)
        overlap_max = min(job_max, profile_max)
        overlap_range = overlap_max - overlap_min

        # How much of the profile's range is covered
        profile_range = profile_max - profile_min
        if profile_range <= 0:
            overlap_pct = 100.0
        else:
            overlap_pct = (overlap_range / profile_range) * 100

        # Score from overlap: 50 base + up to 50 based on coverage
        score = 50.0 + min(overlap_pct * 0.5, 50.0)
        return round(min(score, 100.0), 1)

    def _score_category(self, job: dict[str, Any]) -> float:
        """Score based on job category alignment with profile skills, using taxonomy.

        Resolves the job category to a canonical slug, then compares against
        the profile's ``category_mappings`` (if defined) or direct slug matching.
        """
        job_category = (job.get("category") or "").lower().strip()

        if not job_category or job_category in NO_DATA_VALUES:
            return 50.0  # Neutral — no data

        # Resolve job category to canonical slug via taxonomy
        job_cat_slug = self.taxonomy.resolve(job_category, "category")

        profile_skills = self.profile.get("skills", {})

        # Try profile-driven category mappings first
        category_mappings = self.profile.get("category_mappings", {})
        if isinstance(category_mappings, dict) and category_mappings:
            # Try resolved slug first, then raw category
            mapped_categories = category_mappings.get(job_cat_slug) or category_mappings.get(
                job_category
            )
            if mapped_categories is None:
                return 50.0  # Unknown category → neutral
            if not mapped_categories:
                return 0.0  # Known category but no relevant skills
            for mc in mapped_categories:
                mc_slug = self.taxonomy.resolve(mc, "category")
                if mc_slug in profile_skills and profile_skills[mc_slug]:
                    return 100.0
                # Also check raw category name
                if mc in profile_skills and profile_skills[mc]:
                    return 100.0
            return 0.0

        # Fallback: direct slug matching — resolved job category slug against
        # profile skill category slugs
        if job_cat_slug in profile_skills and profile_skills[job_cat_slug]:
            return 100.0
        # Also try raw category name
        if job_category in profile_skills and profile_skills[job_category]:
            return 100.0

        return 50.0  # No mapping found, neutral

    def _score_experience(self, job: dict[str, Any]) -> float:
        """Score based on experience level / seniority match.

        Uses the profile's optional ``experience_levels`` section to map level
        names to numeric ranks.  Falls back to a default ladder:
        entry → junior → mid → senior → lead → executive.
        """
        profile_years = self.profile.get("experience_years", 0)
        job_level = (job.get("experience_level") or "").lower().strip()

        if not job_level or job_level in NO_DATA_VALUES:
            return 50.0  # Neutral — no data

        # Map profile years to seniority level
        if profile_years < 2:
            profile_level = "junior"
        elif profile_years <= 4:
            profile_level = "mid"
        else:
            profile_level = "senior"

        # Use profile-driven level ranking if available, else default ladder
        level_ranks = self.profile.get("experience_levels")
        if not isinstance(level_ranks, dict) or not level_ranks:
            level_ranks = {
                "entry": 0,
                "junior": 1,
                "mid": 2,
                "senior": 3,
                "lead": 4,
                "executive": 5,
            }

        profile_rank = level_ranks.get(profile_level)

        # Handle combined levels like "mid/senior" — check each part and
        # pick the best match for the profile level.
        levels_to_check: list[str] = [job_level]
        if "/" in job_level:
            levels_to_check = [p.strip() for p in job_level.split("/")]

        best_diff: int | None = None
        for lvl in levels_to_check:
            r = level_ranks.get(lvl)
            if r is not None:
                d = r - profile_rank if profile_rank is not None else 0
                # We want the smallest absolute diff (closest match)
                if best_diff is None or abs(d) < abs(best_diff):
                    best_diff = d

        if best_diff is None or profile_rank is None:
            return 50.0  # Unknown level → neutral

        diff = best_diff

        if diff == 0:
            return 100.0  # Exact match
        elif diff == 1:
            return 100.0  # One step above (reach role) — also perfect
        elif diff == -1:
            return 70.0  # One step below — underqualified but could grow
        else:
            return 30.0  # Two+ steps off

    def _score_soft_keywords(self, job: dict[str, Any], keywords: set[str]) -> float:
        """Soft-curve keyword-presence scorer, shared by behavioral and career fit.

        Neutral (50) when the profile has no keywords, a mild penalty (25) when
        none match, otherwise a 30-base + up-to-70 curve from the match ratio.
        """
        if not keywords:
            return 50.0  # Neutral — no profile data
        found = self._count_keyword_hits(job, keywords)
        if not found:
            return 25.0  # No alignment detected — mild penalty
        ratio = found / len(keywords)
        return round(min(30.0 + ratio * 70.0, 100.0), 1)  # 30 base + up to 70

    def _score_behavioral(self, job: dict[str, Any]) -> float:
        """Score based on behavioral keyword presence using variant-aware text search."""
        return self._score_soft_keywords(job, self.behavioral_keywords)

    def _score_career(self, job: dict[str, Any]) -> float:
        """Score based on career alignment using variant-aware text search."""
        return self._score_soft_keywords(job, self.career_keywords)

    # ---- helpers ----

    def _get_job_skills(self, job: dict[str, Any]) -> list[str]:
        """Extract skills from a job dict, normalizing them via normalize_skills()."""
        raw = job.get("skills", [])
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                logger.debug("Corrupt skills in job — falling back to []")
                raw = []
        return normalize_skills(raw)

    def _get_job_text(self, job: dict[str, Any]) -> str:
        """Combine all text fields for keyword matching."""
        parts = [
            job.get("title", ""),
            job.get("description") or "",
            job.get("category", ""),
            " ".join(job.get("skills", []) if isinstance(job.get("skills"), list) else []),
            job.get("company", ""),
        ]
        return " ".join(parts)


# ---------------------------------------------------------------------------
# Batch scoring
# ---------------------------------------------------------------------------


def score_all_jobs(
    jobs: list[dict[str, Any]],
    profile_path: str = "data/my_profile.yaml",
    sort: bool = True,
    matcher: JobMatcher | None = None,
) -> list[dict[str, Any]]:
    """Score all jobs and return them with scores injected.

    If *matcher* is provided, it is used instead of creating a new one
    (avoids re-parsing the YAML profile on every API call).
    """
    if matcher is None:
        matcher = JobMatcher(profile_path)
    results = []

    for job in jobs:
        details = matcher.score_detail(job)
        enriched = {
            **job,
            "match_score": details["total_score"],
            "match_details": details,
        }
        results.append(enriched)

    if sort:
        results.sort(key=lambda j: j["match_score"], reverse=True)

    return results


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def main():
    """Run matcher on a JSON file and print results."""
    import argparse

    parser = argparse.ArgumentParser(description="Score jobs against profile")
    parser.add_argument(
        "input",
        nargs="?",
        default="data/scraper-output/_all.json",
        help="Input JSON file (default: data/scraper-output/_all.json)",
    )
    parser.add_argument("--profile", default="data/my_profile.yaml", help="Profile YAML path")
    parser.add_argument("--top", type=int, default=10, help="Show top N results (default: 10)")
    args = parser.parse_args()

    # Load jobs
    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Input file not found: {input_path}")
        sys.exit(1)

    with open(input_path) as f:
        jobs = json.load(f)

    # Score
    matcher = JobMatcher(args.profile)

    results = []
    for job in jobs:
        details = matcher.score_detail(job)
        results.append((details["total_score"], job, details))

    results.sort(key=lambda x: x[0], reverse=True)

    # Print results
    print(f"\n{'=' * 80}")
    print(f"  MATCH RESULTS — {len(results)} jobs scored")
    print(f"  Profile: {args.profile}")
    print(f"{'=' * 80}\n")

    for i, (score, job, details) in enumerate(results[: args.top]):
        sal = job.get("salary_max") or "N/A"
        if isinstance(sal, (int, float)):
            currency = resolve_currency(
                job.get("currency"), (matcher.profile.get("rate") or {}).get("currency")
            )
            sal = f"{sal:,.0f} {currency}"
        loc = job.get("location", "?")
        comp = job.get("company", "?")
        title = job.get("title", "?")

        comps = details.get("components", {})
        breakdown = " | ".join(f"{k}: {v['score']:.0f}" for k, v in sorted(comps.items()))

        print(f"  {i + 1:2d}. [{score:5.1f}%] {title}")
        print(f"      {comp} | {sal} | {loc}")
        print(f"      {breakdown}")
        print()

    print(f"{'=' * 80}")


if __name__ == "__main__":
    main()
