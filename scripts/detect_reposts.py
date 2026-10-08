#!/usr/bin/env python3
"""Detect Reposts — find duplicate job postings in the database.

Loads all jobs from the SQLite database, groups them by normalized title
+ company name, and reports clusters of likely duplicates.

Exit codes:
    0  No duplicates found
    1  Duplicates found
    2  Critical error (e.g. database not found)
"""

from __future__ import annotations

import os
import re
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any


# ── Terminal colour support ───────────────────────────────────────────────────

def _supports_color() -> bool:
    if os.environ.get("FORCE_COLOR"):
        return True
    return hasattr(sys.stdout, "isatty") and sys.stdout.isatty()


_USE_COLOR = _supports_color()


def _green(text: str) -> str:
    return f"\033[92m{text}\033[0m" if _USE_COLOR else text


def _yellow(text: str) -> str:
    return f"\033[93m{text}\033[0m" if _USE_COLOR else text


def _red(text: str) -> str:
    return f"\033[91m{text}\033[0m" if _USE_COLOR else text


def _bold(text: str) -> str:
    return f"\033[1m{text}\033[0m" if _USE_COLOR else text


# ── Title normalization ────────────────────────────────────────────────────────

_PUNCTUATION_RE = re.compile(r"[^\w\s]")


def _normalize_title(title: str) -> str:
    """Normalize a job title for comparison.

    Lowercases, strips whitespace, and removes punctuation.
    """
    title = title.lower().strip()
    title = _PUNCTUATION_RE.sub("", title)
    title = re.sub(r"\s+", " ", title).strip()
    return title


# ── Database ───────────────────────────────────────────────────────────────────

def _get_db_path() -> Path:
    """Get the path to the SQLite database."""
    # Try JOB_ENGINE_ROOT env var first
    if env_root := os.getenv("JOB_ENGINE_ROOT"):
        return Path(env_root) / "data" / "job_engine.db"

    # Try relative to script location
    scripts_dir = Path(__file__).resolve().parent
    for parent in [scripts_dir] + list(scripts_dir.parents):
        candidate = parent / "data" / "job_engine.db"
        if candidate.exists():
            return candidate

    # Try config module
    try:
        from job_engine.config import config
        db_path = Path(config.database_url.replace("sqlite:///", ""))
        if db_path.exists():
            return db_path
    except Exception:
        pass

    # Fallback
    return Path.cwd() / "data" / "job_engine.db"


def _connect_db() -> sqlite3.Connection:
    """Connect to the SQLite database."""
    db_path = _get_db_path()
    if not db_path.exists():
        raise RuntimeError(f"Database not found: {db_path}")
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def _load_jobs(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Load all jobs from the database."""
    cursor = conn.execute(
        "SELECT id, title, company_id, platform, url, location, published_at "
        "FROM jobs ORDER BY id"
    )
    return [dict(row) for row in cursor.fetchall()]


def _load_company_name(conn: sqlite3.Connection, company_id: int | None) -> str:
    """Load a company name by ID."""
    if company_id is None:
        return "Unknown"
    cursor = conn.execute("SELECT name FROM companies WHERE id = ?", (company_id,))
    row = cursor.fetchone()
    return row["name"] if row else f"ID:{company_id}"


# ── Duplicate detection ───────────────────────────────────────────────────────

def _find_duplicates(
    jobs: list[dict[str, Any]],
    conn: sqlite3.Connection,
) -> list[list[dict[str, Any]]]:
    """Find duplicate job clusters.

    Groups jobs by (normalized_title, company_id) and returns clusters
    with more than 1 job.
    """
    groups: dict[tuple[str, int | None], list[dict[str, Any]]] = defaultdict(list)

    for job in jobs:
        norm_title = _normalize_title(job["title"])
        company_id = job["company_id"]
        key = (norm_title, company_id)
        groups[key].append(job)

    # Return clusters with more than 1 job, sorted by size
    clusters = [g for g in groups.values() if len(g) > 1]
    clusters.sort(key=lambda c: (-len(c), c[0].get("title", "")))
    return clusters


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> int:
    print()
    print(_bold("Duplicate Job Detection"))
    print()

    # Connect to database
    try:
        conn = _connect_db()
    except RuntimeError as e:
        print(f"  {_red('✗')} {e}")
        print()
        return 2
    except sqlite3.Error as e:
        print(f"  {_red('✗')} Database error: {e}")
        print()
        return 2

    # Load jobs
    try:
        jobs = _load_jobs(conn)
    except sqlite3.Error as e:
        print(f"  {_red('✗')} Failed to load jobs: {e}")
        conn.close()
        return 2

    if not jobs:
        print(f"  {_yellow('⚠')} No jobs found in database")
        print()
        conn.close()
        return 0

    print(f"  Loaded {len(jobs)} jobs from database")
    print()

    # Find duplicates
    clusters = _find_duplicates(jobs, conn)

    if not clusters:
        print(f"  {_green('✓')} No duplicate job postings found")
        print()
        conn.close()
        return 0

    total_duplicates = sum(len(c) for c in clusters)
    print(f"  {_yellow(f'⚠ Found {len(clusters)} duplicate cluster(s)')}"
          f" ({total_duplicates} total jobs affected)")
    print()

    for i, cluster in enumerate(clusters, 1):
        title = cluster[0]["title"]
        company_id = cluster[0]["company_id"]
        company_name = _load_company_name(conn, company_id)

        print(f"  {_bold(f'Cluster #{i}')}: {title} @ {company_name} ({len(cluster)} jobs)")
        for job in cluster:
            loc = job.get("location") or "N/A"
            pub = job.get("published_at") or "N/A"
            print(f"    ID:{job['id']:>6d}  {job['platform']:20s}  {job['url']}")
        print()

    conn.close()
    return 1


if __name__ == "__main__":
    sys.exit(main())