#!/usr/bin/env python3
"""Database Integrity Check — verify the SQLite database is healthy.

Runs PRAGMA integrity_check, checks foreign key consistency, looks for
orphaned rows, and reports findings.

Exit codes:
    0  Database is clean
    1  Warnings (non-critical issues found)
    2  Integrity failure (critical issues found)
"""

from __future__ import annotations

import os
import sqlite3
import sys
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


# ── Database ───────────────────────────────────────────────────────────────────

def _get_db_path() -> Path:
    """Get the path to the SQLite database."""
    if env_root := os.getenv("JOB_ENGINE_ROOT"):
        return Path(env_root) / "data" / "job_engine.db"

    scripts_dir = Path(__file__).resolve().parent
    for parent in [scripts_dir] + list(scripts_dir.parents):
        candidate = parent / "data" / "job_engine.db"
        if candidate.exists():
            return candidate

    try:
        from job_engine.config import config
        db_path = Path(config.database_url.replace("sqlite:///", ""))
        if db_path.exists():
            return db_path
    except Exception:
        pass

    return Path.cwd() / "data" / "job_engine.db"


def _connect_db() -> sqlite3.Connection:
    """Connect to the SQLite database."""
    db_path = _get_db_path()
    if not db_path.exists():
        raise RuntimeError(f"Database not found: {db_path}")
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


# ── Checks ────────────────────────────────────────────────────────────────────

def _check_integrity(conn: sqlite3.Connection) -> list[str]:
    """Run PRAGMA integrity_check and return any issues found."""
    cursor = conn.execute("PRAGMA integrity_check")
    rows = cursor.fetchall()
    issues = []
    for row in rows:
        val = row[0] if isinstance(row, sqlite3.Row) else row[0]
        if val != "ok":
            issues.append(val)
    return issues


def _check_foreign_keys(conn: sqlite3.Connection) -> dict[str, list[str]]:
    """Check foreign key consistency across all tables.

    Returns a dict mapping table/constraint name to a list of issues.
    """
    issues: dict[str, list[str]] = {}

    # Jobs with missing company_id
    cursor = conn.execute(
        "SELECT j.id, j.title, j.company_id "
        "FROM jobs j "
        "LEFT JOIN companies c ON j.company_id = c.id "
        "WHERE j.company_id IS NOT NULL AND c.id IS NULL"
    )
    rows = cursor.fetchall()
    if rows:
        paths = [f"job ID:{r['id']} (company_id:{r['company_id']})" for r in rows]
        issues["jobs → companies (orphan company_id)"] = paths

    # Applications with missing job_id
    cursor = conn.execute(
        "SELECT a.id, a.job_id "
        "FROM applications a "
        "LEFT JOIN jobs j ON a.job_id = j.id "
        "WHERE j.id IS NULL"
    )
    rows = cursor.fetchall()
    if rows:
        paths = [f"application ID:{r['id']} (job_id:{r['job_id']})" for r in rows]
        issues["applications → jobs (orphan job_id)"] = paths

    # Application logs with missing application_id
    cursor = conn.execute(
        "SELECT al.id, al.application_id "
        "FROM application_logs al "
        "LEFT JOIN applications a ON al.application_id = a.id "
        "WHERE a.id IS NULL"
    )
    rows = cursor.fetchall()
    if rows:
        paths = [f"application_log ID:{r['id']} (application_id:{r['application_id']})" for r in rows]
        issues["application_logs → applications (orphan application_id)"] = paths

    # Job taxonomy terms with missing job_id
    cursor = conn.execute(
        "SELECT jtt.id, jtt.job_id "
        "FROM job_taxonomy_terms jtt "
        "LEFT JOIN jobs j ON jtt.job_id = j.id "
        "WHERE j.id IS NULL"
    )
    rows = cursor.fetchall()
    if rows:
        paths = [f"job_taxonomy_terms ID:{r['id']} (job_id:{r['job_id']})" for r in rows]
        issues["job_taxonomy_terms → jobs (orphan job_id)"] = paths

    # Job taxonomy terms with missing term_id
    cursor = conn.execute(
        "SELECT jtt.id, jtt.term_id "
        "FROM job_taxonomy_terms jtt "
        "LEFT JOIN taxonomy_terms t ON jtt.term_id = t.id "
        "WHERE t.id IS NULL"
    )
    rows = cursor.fetchall()
    if rows:
        paths = [f"job_taxonomy_terms ID:{r['id']} (term_id:{r['term_id']})" for r in rows]
        issues["job_taxonomy_terms → taxonomy_terms (orphan term_id)"] = paths

    # Taxonomy synonyms with missing term_id
    cursor = conn.execute(
        "SELECT ts.id, ts.term_id "
        "FROM taxonomy_synonyms ts "
        "LEFT JOIN taxonomy_terms t ON ts.term_id = t.id "
        "WHERE t.id IS NULL"
    )
    rows = cursor.fetchall()
    if rows:
        paths = [f"taxonomy_synonyms ID:{r['id']} (term_id:{r['term_id']})" for r in rows]
        issues["taxonomy_synonyms → taxonomy_terms (orphan term_id)"] = paths

    return issues


def _check_table_health(conn: sqlite3.Connection) -> dict[str, Any]:
    """Check general table health: row counts, missing data, etc.

    Returns a dict with table stats and any warnings.
    """
    stats: dict[str, Any] = {
        "tables": {},
        "warnings": [],
    }

    tables = [
        "jobs",
        "companies",
        "applications",
        "application_logs",
        "scraper_logs",
        "taxonomy_terms",
        "taxonomy_synonyms",
        "job_taxonomy_terms",
    ]

    for table in tables:
        try:
            cursor = conn.execute(f"SELECT COUNT(*) as cnt FROM {table}")
            row = cursor.fetchone()
            stats["tables"][table] = row["cnt"] if row else 0
        except sqlite3.Error:
            stats["tables"][table] = -1  # table doesn't exist

    # Check for jobs with empty titles
    cursor = conn.execute("SELECT COUNT(*) as cnt FROM jobs WHERE title IS NULL OR title = ''")
    row = cursor.fetchone()
    if row and row["cnt"] > 0:
        stats["warnings"].append(f"{row['cnt']} job(s) with empty title")

    # Check for jobs with no company_id
    cursor = conn.execute("SELECT COUNT(*) as cnt FROM jobs WHERE company_id IS NULL")
    row = cursor.fetchone()
    if row and row["cnt"] > 0:
        stats["warnings"].append(f"{row['cnt']} job(s) with no company (company_id is NULL)")

    # Check for duplicate external_id + platform combos
    cursor = conn.execute(
        "SELECT external_id, platform, COUNT(*) as cnt "
        "FROM jobs "
        "GROUP BY external_id, platform "
        "HAVING cnt > 1"
    )
    rows = cursor.fetchall()
    if rows:
        total_dup = sum(r["cnt"] for r in rows)
        stats["warnings"].append(
            f"{len(rows)} duplicate external_id+platform combo(s) "
            f"({total_dup} total rows affected)"
        )

    return stats


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> int:
    print()
    print(_bold("Database Integrity Check"))
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

    db_path = _get_db_path()
    db_size = db_path.stat().st_size / (1024 * 1024)
    print(f"  Database: {db_path} ({db_size:.1f} MB)")
    print()

    exit_code = 0

    # ── 1. PRAGMA integrity_check ──────────────────────────────────────────────
    print(f"  {_bold('1. SQLite Integrity Check')}")
    try:
        issues = _check_integrity(conn)
        if not issues:
            print(f"    {_green('✓')} PRAGMA integrity_check passed")
        else:
            exit_code = 2
            for issue in issues:
                print(f"    {_red('✗')} {issue}")
    except sqlite3.Error as e:
        print(f"    {_red('✗')} Integrity check failed: {e}")
        exit_code = 2
    print()

    # ── 2. Foreign Key Consistency ─────────────────────────────────────────────
    print(f"  {_bold('2. Foreign Key Consistency')}")
    try:
        fk_issues = _check_foreign_keys(conn)
        if not fk_issues:
            print(f"    {_green('✓')} All foreign keys are consistent")
        else:
            if exit_code < 2:
                exit_code = 1
            for constraint, paths in fk_issues.items():
                print(f"    {_yellow('⚠')} {constraint}:")
                for path in paths[:5]:  # Show first 5
                    print(f"      - {path}")
                if len(paths) > 5:
                    print(f"      ... and {len(paths) - 5} more")
    except sqlite3.Error as e:
        print(f"    {_red('✗')} Foreign key check failed: {e}")
        exit_code = 2
    print()

    # ── 3. Table Health ────────────────────────────────────────────────────────
    print(f"  {_bold('3. Table Health')}")
    try:
        health = _check_table_health(conn)

        for table, count in sorted(health["tables"].items()):
            if count >= 0:
                print(f"    {_green('✓')} {table:25s} {count:>8,} rows")
            else:
                print(f"    {_yellow('⚠')} {table:25s} {_yellow('table not found')}")

        if health["warnings"]:
            if exit_code < 2:
                exit_code = 1
            for warning in health["warnings"]:
                print(f"    {_yellow('⚠')} {warning}")

        if not health["warnings"]:
            print(f"    {_green('✓')} No table health warnings")

    except sqlite3.Error as e:
        print(f"    {_red('✗')} Table health check failed: {e}")
        if exit_code < 2:
            exit_code = 1
    print()

    # ── Summary ────────────────────────────────────────────────────────────────
    if exit_code == 0:
        print(f"  {_green('Database integrity check passed')}")
    elif exit_code == 1:
        print(f"  {_yellow('Database has warnings (non-critical)')}")
    else:
        print(f"  {_red('Database has integrity failures')}")
    print()

    conn.close()
    return exit_code


if __name__ == "__main__":
    sys.exit(main())