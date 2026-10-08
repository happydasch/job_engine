#!/usr/bin/env python3
"""
Database Cleanup — fixes broken data accumulated by early scraper bugs.

Issues fixed:
1. Indeed location-contaminated company names (e.g. "JPMorganChaseNew York, NY")
2. Reddit usernames as company names (e.g. "u/Aaryan24shah")
3. CSS blob as company name (e.g. ".mosaic-provider-jobcards-...")
4. NULL company_id for jobs without a company
5. Deprecated `company` column still in the jobs table

Usage:
    python -m job_engine.cleanup_db          # dry-run (preview changes)
    python -m job_engine.cleanup_db --apply   # actually apply changes
    python -m job_engine.cleanup_db --verify-only  # just health check
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field

from job_engine.database import get_sync_engine
from job_engine.models import Company
from sqlalchemy import inspect, select, text
from sqlalchemy.orm import Session

# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------


@dataclass
class FixReport:
    """Collects what the cleanup would do / did."""

    company_renames: list[tuple[int, str, str]] = field(default_factory=list)
    company_splits: list[tuple[int, str, str, str]] = field(default_factory=list)
    company_moves: list[tuple[int, str, int, str]] = field(default_factory=list)
    location_updates: list[tuple[int, str, str]] = field(default_factory=list)
    null_company_fixes: list[tuple[int, str, str]] = field(default_factory=list)
    column_dropped: bool = False
    orphan_companies_deleted: list[int] = field(default_factory=list)

    @property
    def total_actions(self) -> int:
        return (
            len(self.company_renames)
            + len(self.company_splits)
            + len(self.company_moves)
            + len(self.location_updates)
            + len(self.null_company_fixes)
            + (1 if self.column_dropped else 0)
            + len(self.orphan_companies_deleted)
        )

    def print_summary(self) -> None:
        print(f"\n{'=' * 60}")
        print("  DATABASE CLEANUP REPORT")
        print(f"{'=' * 60}")
        if self.company_splits:
            print(f"\n  Company+location splits:   {len(self.company_splits)}")
            for cid, old, new_comp, new_loc in self.company_splits[:5]:
                print(f"    co#{cid}: {old!r}")
                print(f"      -> company: {new_comp!r}")
                print(f"      -> location: {new_loc!r}")
            if len(self.company_splits) > 5:
                print(f"    ... and {len(self.company_splits) - 5} more")
        if self.company_renames:
            print(f"\n  Company renames:           {len(self.company_renames)}")
            for cid, old, new in self.company_renames[:5]:
                print(f"    co#{cid}: {old!r} -> {new!r}")
            if len(self.company_renames) > 5:
                print(f"    ... and {len(self.company_renames) - 5} more")
        if self.company_moves:
            print(f"\n  Jobs moved to better company: {len(self.company_moves)}")
            for jid, old, new_cid, new_name in self.company_moves[:5]:
                print(f"    job#{jid}: {old!r} -> co#{new_cid} {new_name!r}")
            if len(self.company_moves) > 5:
                print(f"    ... and {len(self.company_moves) - 5} more")
        if self.location_updates:
            print(f"\n  Location fixes:             {len(self.location_updates)}")
            for jid, old, new in self.location_updates[:5]:
                print(f"    job#{jid}: {old!r} -> {new!r}")
            if len(self.location_updates) > 5:
                print(f"    ... and {len(self.location_updates) - 5} more")
        if self.null_company_fixes:
            print(f"\n  NULL company_id fixes:      {len(self.null_company_fixes)}")
            for jid, plat, fix in self.null_company_fixes:
                print(f"    job#{jid} ({plat}): -> {fix!r}")
        if self.column_dropped:
            print("\n  Dropped deprecated `company` column")
        if self.orphan_companies_deleted:
            print(f"\n  Orphan companies removed:   {len(self.orphan_companies_deleted)}")
        print(f"\n  TOTAL ACTIONS: {self.total_actions}")
        print(f"{'=' * 60}\n")


# ---------------------------------------------------------------------------
# Company name -> location splitting heuristics
# ---------------------------------------------------------------------------

# Location-suffix markers (checked after stripping title from description)
_LOCATION_MARKER = re.compile(
    r"(?:"
    r"(Remote|Hybrid)\s+(?:in|work\s+in)\s+"  # "Remote in ..." / "Hybrid work in ..."
    r"|"
    r"(Remote)\s*$"  # "Remote" at end
    r")",
    re.IGNORECASE,
)


def extract_company_from_description(description: str, title: str) -> tuple[str, str]:
    """Extract clean company name and location from Indeed job description.

    Indeed description format is:
      TitleCompanyNameRemote in Location...
      or
      TitleCompanyNameNew York, NY...

    We strip the title, then find where the company name ends and location
    begins by looking for location markers.
    """
    if not description or not title:
        return ("", "")

    # Strip the title from the beginning of the description
    text = description.strip()
    if text.startswith(title):
        text = text[len(title) :].strip()

    # Remove CSS junk (Indeed embeds CSS in the card text)
    text = re.sub(r"\.[\w-]+\{[^}]*\}", "", text)
    text = re.sub(r"\s+", " ", text).strip()

    # --- Strategy 1: explicit location markers ---
    m = _LOCATION_MARKER.search(text)
    if m:
        company = text[: m.start()].strip()
        location = text[m.start() :].strip()
        # Cut off trailing junk after the location
        location = re.split(r"\n|View\s+(all|similar)|More|…", location, maxsplit=1)[0].strip()
        if company:
            return (company, location)

    # --- Strategy 2: City, STATE [ZIP] [(area)] near end ---
    m = re.search(
        r"([A-Z][a-zA-Z\s]+),\s*([A-Z]{2})(?:\s+\d{5})?(?:\s*\([^)]*\))?",
        text,
    )
    if m:
        city_start = m.start(1)
        state = m.group(2).upper()
        if state in _US_STATES:
            company = text[:city_start].strip()
            location = text[city_start:].strip()
            # Cut off trailing junk
            location = re.split(r"\n|View\s+(all|similar|$)", location, maxsplit=1)[0].strip()
            if company:
                return (company, location)

    return ("", "")


def split_company_location(combined: str) -> tuple[str, str]:
    """Fallback: split a company+location string like 'JPMorganChaseNew York, NY'.

    Only used when description-based extraction fails.
    """
    if not combined:
        return ("Unknown", "")

    combined = combined.strip()

    # Explicit markers
    for marker in ["Remote in ", "Hybrid work in ", "Hybrid in "]:
        idx = combined.lower().find(marker.lower())
        if idx >= 0:
            company = combined[:idx].strip()
            location = combined[idx:].strip()
            if company:
                return (company, location)

    # "Remote" at end (only if preceded by non-letter)
    m = re.search(r"Remote\s*$", combined)
    if m:
        company = combined[: m.start()].strip()
        if company:
            return (company, "Remote")

    # Find ", STATE [ZIP] [(area)]" at end. Walk backwards to find split.
    m = re.search(r",\s*([A-Z]{2})(?:\s+\d{5})?(?:\s*\([^)]*\))?\s*$", combined)
    if m:
        state = m.group(1).upper()
        if state in _US_STATES:
            comma_pos = m.start()
            # Walk backwards to find city start: we look for where an uppercase
            # city name follows a word ending in lowercase
            walk = comma_pos - 1
            while walk >= 0 and combined[walk].isspace():
                walk -= 1
            if walk < 0:
                return (combined, "")
            # Walk backwards through alpha chars to find start of last word
            while walk >= 0 and (combined[walk].isalpha() or combined[walk] in "'-"):
                walk -= 1
            word_start = walk + 1

            # Collect multi-word city (walk backwards for more uppercase-starting words)
            while word_start > 1:
                prev = word_start - 1
                if combined[prev].isspace():
                    # Find where the preceding word starts
                    p = prev - 1
                    while p >= 0 and (combined[p].isalpha() or combined[p] in "'-"):
                        p -= 1
                    prev_word_start = p + 1
                    if combined[prev_word_start].isupper():
                        # Check if preceding word is a company suffix
                        preceding = combined[prev_word_start:prev].strip().rstrip(".")
                        if preceding.lower() in _COMPANY_SUFFIXES:
                            break
                        word_start = prev_word_start
                    else:
                        break
                else:
                    break

            company = combined[:word_start].strip()
            location = combined[word_start:].strip()
            if company:
                return (company, location)

    return (combined, "")


# Known US state abbreviations
_US_STATES = frozenset(
    {
        "AL",
        "AK",
        "AZ",
        "AR",
        "CA",
        "CO",
        "CT",
        "DE",
        "DC",
        "FL",
        "GA",
        "HI",
        "ID",
        "IL",
        "IN",
        "IA",
        "KS",
        "KY",
        "LA",
        "ME",
        "MD",
        "MA",
        "MI",
        "MN",
        "MS",
        "MO",
        "MT",
        "NE",
        "NV",
        "NH",
        "NJ",
        "NM",
        "NY",
        "NC",
        "ND",
        "OH",
        "OK",
        "OR",
        "PA",
        "RI",
        "SC",
        "SD",
        "TN",
        "TX",
        "UT",
        "VT",
        "VA",
        "WA",
        "WV",
        "WI",
        "WY",
    }
)

# Company suffixes — text after these is likely location, not company
_COMPANY_SUFFIXES = frozenset(
    {
        "inc",
        "llc",
        "corp",
        "co",
        "ltd",
        "gmbh",
        "sa",
        "plc",
        "pvt",
        "services",
        "group",
        "technologies",
        "solutions",
        "systems",
        "international",
        "company",
        "corporation",
        "industries",
        "partners",
        "associates",
        "consulting",
        "management",
        "llp",
        "limited",
        "holding",
        "holdings",
    }
)


# Known US state abbreviations
_US_STATES = frozenset(
    {
        "AL",
        "AK",
        "AZ",
        "AR",
        "CA",
        "CO",
        "CT",
        "DE",
        "DC",
        "FL",
        "GA",
        "HI",
        "ID",
        "IL",
        "IN",
        "IA",
        "KS",
        "KY",
        "LA",
        "ME",
        "MD",
        "MA",
        "MI",
        "MN",
        "MS",
        "MO",
        "MT",
        "NE",
        "NV",
        "NH",
        "NJ",
        "NM",
        "NY",
        "NC",
        "ND",
        "OH",
        "OK",
        "OR",
        "PA",
        "RI",
        "SC",
        "SD",
        "TN",
        "TX",
        "UT",
        "VT",
        "VA",
        "WA",
        "WV",
        "WI",
        "WY",
    }
)


# ---------------------------------------------------------------------------
# Check heuristics
# ---------------------------------------------------------------------------


def looks_clean(name: str) -> bool:
    """True if a company name appears clean (no location contamination)."""
    if not name:
        return False
    # Check for location markers
    if re.search(
        r",\s*(?:AZ|CA|CO|CT|DC|DE|FL|GA|IL|IN|MA|MD|MI|MN|NC|NJ|NY|OH|OR|PA|TN|TX|VA|WA|WI)\b",
        name,
    ):
        return False
    if re.search(r"\bremote\s+(?:in|work)\b", name.lower()):
        return False
    if re.search(r"\bhybrid\s+(?:work\s+)?in\b", name.lower()):
        return False
    if name.lower().strip().endswith("remote") and len(name) > 10:
        return False
    return True


# ---------------------------------------------------------------------------
# Indeed fixing
# ---------------------------------------------------------------------------


def fix_indeed_jobs(session: Session, report: FixReport, dry_run: bool) -> None:
    """Fix Indeed jobs where location was concatenated into company name.

    Uses two strategies:
    1. Primary: extract clean company/location from the job description text
    2. Fallback: split company+location combined string via heuristics
    """
    rows = session.execute(
        text("""
            SELECT DISTINCT j.id AS job_id, j.title, c.id AS company_id,
                   c.name AS company_name, j.location AS job_location,
                   j.description AS job_description
            FROM jobs j
            JOIN companies c ON j.company_id = c.id
            WHERE j.platform = 'indeed.com'
            ORDER BY j.id
        """)
    ).all()

    for row in rows:
        job_id = row.job_id
        company_id = row.company_id
        company_name = row.company_name
        desc = row.job_description or ""

        if looks_clean(company_name):
            continue

        # Strategy 1: extract from description (most reliable)
        clean_company, clean_location = extract_company_from_description(desc, row.title)

        # Validate: company must be non-empty and different from the broken name
        if clean_company and clean_company != company_name and clean_company != row.title:
            report.company_splits.append((company_id, company_name, clean_company, clean_location))
            if not dry_run:
                _rename_company(session, company_id, clean_company)

                # Update location on all jobs under this company
                affected = session.execute(
                    text("SELECT id, location FROM jobs WHERE company_id = :cid"),
                    {"cid": company_id},
                ).all()
                for aff in affected:
                    loc = aff.location or ""
                    if (
                        not loc
                        or loc == company_name
                        or (clean_location and clean_location not in loc)
                    ):
                        new_loc = clean_location or "Remote"
                        session.execute(
                            text("UPDATE jobs SET location = :loc WHERE id = :jid"),
                            {"loc": new_loc, "jid": aff.id},
                        )
                        if aff.id == job_id:
                            report.location_updates.append((aff.id, loc, new_loc))

        else:
            # Strategy 2: fallback to splitting company+location combined string
            clean_company, clean_location = split_company_location(company_name)

            if clean_company and clean_location and clean_company != company_name:
                report.company_splits.append(
                    (company_id, company_name, clean_company, clean_location)
                )
                if not dry_run:
                    _rename_company(session, company_id, clean_company)

                    affected = session.execute(
                        text("SELECT id, location FROM jobs WHERE company_id = :cid"),
                        {"cid": company_id},
                    ).all()
                    for aff in affected:
                        loc = aff.location or ""
                        if not loc or loc == company_name:
                            session.execute(
                                text("UPDATE jobs SET location = :loc WHERE id = :jid"),
                                {"loc": clean_location, "jid": aff.id},
                            )
                            if aff.id == job_id:
                                report.location_updates.append((aff.id, loc, clean_location))


def _rename_company(session: Session, company_id: int, new_name: str) -> None:
    """Rename a company. If target name exists, merge jobs into it."""
    existing = session.execute(select(Company).where(Company.name == new_name)).scalar_one_or_none()

    if existing and existing.id != company_id:
        session.execute(
            text("UPDATE jobs SET company_id = :target WHERE company_id = :source"),
            {"target": existing.id, "source": company_id},
        )
        session.execute(text("DELETE FROM companies WHERE id = :cid"), {"cid": company_id})
    else:
        session.execute(
            text("UPDATE companies SET name = :name WHERE id = :id"),
            {"name": new_name, "id": company_id},
        )


# ---------------------------------------------------------------------------
# Reddit fixing
# ---------------------------------------------------------------------------


def fix_reddit_jobs(session: Session, report: FixReport, dry_run: bool) -> None:
    """Fix Reddit jobs where 'u/username' is used as the company name."""
    rows = session.execute(
        text("""
            SELECT j.id AS job_id, j.title, c.id AS company_id,
                   c.name AS company_name, j.description AS job_description
            FROM jobs j
            JOIN companies c ON j.company_id = c.id
            WHERE j.platform = 'reddit.com'
              AND c.name LIKE 'u/%'
            ORDER BY j.id
        """)
    ).all()

    for row in rows:
        company_id = row.company_id
        company_name = row.company_name
        desc = row.job_description or ""

        extracted = _extract_from_reddit_post(desc, row.title)
        final_company = extracted or "Reddit (r/forhire)"

        if final_company != company_name:
            report.company_renames.append((company_id, company_name, final_company))
            if not dry_run:
                _rename_company(session, company_id, final_company)


# Patterns to find real company names in Reddit post text
_REDDIT_EXTRACT_PATTERNS = [
    # "at Company" or "with Company" or "for Company"
    re.compile(
        r"\b(?:at|with|for|@)\s+([A-Z][A-Za-z0-9'.& ]+?)(?:\s+(?:in|as|is|to|the|-|[,(]|\||$))",
        re.IGNORECASE,
    ),
    # "Company is hiring"
    re.compile(
        r"^([A-Z][A-Za-z0-9'.& ]+?)\s+(?:is\s+)?hiring\b",
        re.IGNORECASE | re.MULTILINE,
    ),
    # "| CompanyName |" (pipe-delimited)
    re.compile(r"\|\s*([A-Z][A-Za-z0-9'.& ]{2,60}?)\s*\|"),
    # "Looking for X at Y" — extract Y
    re.compile(
        r"(?:looking|searching|hiring)\s+(?:for\s+)?(?:a\s+)?\w+\s+(?:at|for)\s+"
        r"([A-Z][A-Za-z0-9'.& ]+?)(?:\s*[,(]|\s*\||$)",
        re.IGNORECASE,
    ),
]


def _extract_from_reddit_post(desc: str, title: str) -> str | None:
    if not desc:
        return None
    text = (title + " " + desc)[:1500]

    for pattern in _REDDIT_EXTRACT_PATTERNS:
        m = pattern.search(text)
        if m:
            company = m.group(1).strip()
            company = re.sub(r"\s+", " ", company).strip()
            # Reject obvious non-companies
            if (
                company.lower().startswith("u/")
                or len(company) < 3
                or "[" in company
                or "<" in company
            ):
                continue
            return company
    return None


# ---------------------------------------------------------------------------
# CSS blob fix
# ---------------------------------------------------------------------------


def fix_css_blob_companies(session: Session, report: FixReport, dry_run: bool) -> None:
    """Fix companies whose names are CSS class blobs (>100 chars, starting with '.')."""
    rows = session.execute(
        text("""
            SELECT c.id, c.name, LENGTH(c.name) AS name_len
            FROM companies c
            WHERE LENGTH(c.name) > 100
            ORDER BY name_len DESC
        """)
    ).all()

    for row in rows:
        company_id = row.id
        company_name = row.name

        # Find jobs for this company
        jobs = session.execute(
            text("""
                SELECT j.id, j.title, j.description
                FROM jobs j
                WHERE j.company_id = :cid
                LIMIT 10
            """),
            {"cid": company_id},
        ).all()

        for job in jobs:
            desc = job.description or ""
            title = job.title or ""

            # Strip CSS junk from description
            clean_text = re.sub(r"\.[\w-]+\{[^}]*\}", "", desc)
            clean_text = re.sub(r"\s+", " ", clean_text).strip()

            if clean_text and len(clean_text) > 5:
                if title and clean_text.startswith(title):
                    after_title = clean_text[len(title) :].strip()
                    company_candidate, _ = split_company_location(after_title)
                    if company_candidate and len(company_candidate) > 2:
                        report.company_renames.append((company_id, company_name, company_candidate))
                        if not dry_run:
                            _rename_company(session, company_id, company_candidate)
                        return

        # Last resort
        report.company_renames.append((company_id, company_name, "Unknown"))
        if not dry_run:
            _rename_company(session, company_id, "Unknown")


# ---------------------------------------------------------------------------
# NULL company_id fix
# ---------------------------------------------------------------------------


def fix_null_companies(session: Session, report: FixReport, dry_run: bool) -> None:
    """Set company_id for jobs that have none."""
    rows = session.execute(
        text("""
            SELECT j.id, j.platform, j.title
            FROM jobs j
            WHERE j.company_id IS NULL
            ORDER BY j.id
        """)
    ).all()

    if not rows:
        return

    # Ensure "Unknown" company exists
    unknown = session.execute(select(Company).where(Company.name == "Unknown")).scalar_one_or_none()
    if not unknown:
        unknown = Company(name="Unknown")
        session.add(unknown)
        session.flush()

    for row in rows:
        report.null_company_fixes.append((row.id, row.platform, f"co#{unknown.id} 'Unknown'"))
        if not dry_run:
            session.execute(
                text("UPDATE jobs SET company_id = :cid WHERE id = :jid"),
                {"cid": unknown.id, "jid": row.id},
            )


# ---------------------------------------------------------------------------
# Drop deprecated column
# ---------------------------------------------------------------------------


def drop_deprecated_column(engine, report: FixReport, dry_run: bool) -> None:
    """Drop the old `company` column if it exists."""
    inspector = inspect(engine)
    columns = [c["name"] for c in inspector.get_columns("jobs")]
    if "company" not in columns:
        return

    report.column_dropped = True
    if not dry_run:
        with Session(engine) as session:
            session.execute(text("ALTER TABLE jobs DROP COLUMN company"))
            session.commit()
            print("Dropped deprecated `company` column from jobs table")


# ---------------------------------------------------------------------------
# Remove orphan companies
# ---------------------------------------------------------------------------


def remove_orphan_companies(session: Session, report: FixReport, dry_run: bool) -> None:
    """Delete companies that have no associated jobs."""
    orphans = session.execute(
        text("""
            SELECT c.id, c.name
            FROM companies c
            LEFT JOIN jobs j ON j.company_id = c.id
            WHERE j.id IS NULL
        """)
    ).all()

    for row in orphans:
        report.orphan_companies_deleted.append(row.id)
        if not dry_run:
            session.execute(text("DELETE FROM companies WHERE id = :cid"), {"cid": row.id})


# ---------------------------------------------------------------------------
# Verify
# ---------------------------------------------------------------------------


def verify(engine) -> dict:
    """Return a snapshot of key data-health metrics."""
    with Session(engine) as session:
        total_companies = session.execute(text("SELECT COUNT(*) FROM companies")).scalar()
        total_jobs = session.execute(text("SELECT COUNT(*) FROM jobs")).scalar()
        null_company = session.execute(
            text("SELECT COUNT(*) FROM jobs WHERE company_id IS NULL")
        ).scalar()
        empty_loc = session.execute(
            text("SELECT COUNT(*) FROM jobs WHERE location IS NULL OR location = ''")
        ).scalar()
        indeed_broken = session.execute(
            text("""
                SELECT COUNT(*) FROM jobs j
                JOIN companies c ON j.company_id = c.id
                WHERE j.platform = 'indeed.com'
                  AND c.name LIKE '%, %'
            """)
        ).scalar()
        reddit_left = session.execute(
            text("""
                SELECT COUNT(*) FROM jobs j
                JOIN companies c ON j.company_id = c.id
                WHERE j.platform = 'reddit.com' AND c.name LIKE 'u/%'
            """)
        ).scalar()
        css_left = session.execute(
            text("SELECT COUNT(*) FROM companies WHERE LENGTH(name) > 100")
        ).scalar()

    cols = [c["name"] for c in inspect(engine).get_columns("jobs")]
    return {
        "total_companies": total_companies,
        "total_jobs": total_jobs,
        "null_company_id": null_company,
        "empty_location": empty_loc,
        "indeed_broken": indeed_broken,
        "reddit_usernames": reddit_left,
        "css_blobs": css_left,
        "has_company_column": "company" in cols,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description="Clean up broken data in the job database.")
    parser.add_argument(
        "--apply", action="store_true", help="Actually apply changes (default: dry-run)"
    )
    parser.add_argument("--verify-only", action="store_true", help="Just run health check")
    args = parser.parse_args()

    engine = get_sync_engine()
    dry_run = not args.apply

    if args.verify_only:
        s = verify(engine)
        print("\nDATABASE HEALTH CHECK")
        print("=" * 40)
        for k, v in s.items():
            print(f"  {k}: {v}")
        return 0

    print(f"\n{'=' * 60}")
    print(f"  {'DRY RUN' if dry_run else 'APPLYING CHANGES'}")
    print(f"{'=' * 60}")

    report = FixReport()

    with Session(engine) as session:
        fix_css_blob_companies(session, report, dry_run)
        fix_indeed_jobs(session, report, dry_run)
        fix_reddit_jobs(session, report, dry_run)
        fix_null_companies(session, report, dry_run)
        remove_orphan_companies(session, report, dry_run)

        if not dry_run:
            session.commit()
            print("Changes committed")
        else:
            session.rollback()

    drop_deprecated_column(engine, report, dry_run)

    report.print_summary()

    s = verify(engine)
    print("POST-CLEANUP VERIFICATION")
    print("=" * 40)
    for k, v in s.items():
        print(f"  {k}: {v}")

    if dry_run:
        print("\nRun with --apply to commit these changes")

    return 0


if __name__ == "__main__":
    sys.exit(main())
