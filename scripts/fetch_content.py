#!/usr/bin/env python3
"""Batch fetch content for jobs with empty descriptions.

Queries the database for jobs that have an empty description and a URL,
then fetches each URL via HTTP GET, extracts readable text, and persists
the result to the ``fetched_content`` column.

Usage:
    python scripts/fetch_content.py                        # all jobs with empty description
    python scripts/fetch_content.py --limit 10             # first 10 jobs only
    python scripts/fetch_content.py --overwrite            # refetch even if already fetched
    python scripts/fetch_content.py --llm                  # also trigger LLM analysis after fetch
"""

import argparse
import logging
import re
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import httpx
from job_engine.database import get_sync_engine
from job_engine.models import Job
from sqlalchemy.orm import Session

# Ensure the project root is on sys.path so that `job_engine` is importable
_root = Path(__file__).resolve().parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

logger = logging.getLogger(__name__)


def _extract_text_from_html(content: str) -> str:
    """Strip a job page's HTML down to readable text (block structure preserved)."""
    # Remove script and style blocks
    for tag in ("script", "style", "noscript", "svg"):
        content = re.sub(
            rf"<{tag}[^>]*>.*?</{tag}>",
            "",
            content,
            flags=re.DOTALL | re.IGNORECASE,
        )
    # Add newlines after block-level closing tags
    for tag in (
        "/p",
        "/div",
        "/li",
        "/tr",
        "/section",
        "/article",
        "/blockquote",
        "/pre",
        "/h1",
        "/h2",
        "/h3",
        "/h4",
        "/h5",
        "/h6",
        "br[/>]",
        "/ul",
        "/ol",
        "/dl",
        "/table",
    ):
        content = re.sub(rf"(?i)<{tag}\s*>", "\n", content)
    # Convert <li> to bullet points
    content = re.sub(r"(?i)<li[^>]*>\s*", "  • ", content)
    # Strip remaining HTML tags
    content = re.sub(r"<[^>]+>", " ", content)
    # Decode common HTML entities
    for ent, ch in [
        ("&amp;", "&"),
        ("&lt;", "<"),
        ("&gt;", ">"),
        ("&nbsp;", " "),
        ("&quot;", '"'),
        ("&#39;", "'"),
        ("&apos;", "'"),
    ]:
        content = content.replace(ent, ch)
    # Collapse horizontal whitespace but keep newlines
    content = re.sub(r"[ \t]+", " ", content)
    # Remove excessive blank lines
    content = re.sub(r"\n{3,}", "\n\n", content)
    return content.strip()[:100000]


def fetch_and_store(job: Job, client: httpx.Client, overwrite: bool = False) -> bool:
    """Fetch a job's URL, extract text, and store in fetched_content.

    Returns True if content was fetched and stored, False otherwise.
    """
    if not job.url:
        return False

    if job.fetched_content and not overwrite:
        return False  # Already fetched and not overwriting

    try:
        resp = client.get(
            job.url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            },
            timeout=30,
            follow_redirects=True,
        )
        resp.raise_for_status()
        content = _extract_text_from_html(resp.text)
    except Exception as exc:
        logger.warning("  Failed to fetch %s: %s", job.url, exc)
        return False

    if not content.strip():
        logger.warning("  Empty content for %s", job.url)
        return False

    # Persist to DB
    engine = get_sync_engine()
    with Session(engine) as session:
        db_job = session.query(Job).filter(Job.id == job.id).first()
        if db_job:
            db_job.fetched_content = content
            db_job.updated_at = datetime.now(UTC)
            session.commit()
            return True
    return False


def main():
    parser = argparse.ArgumentParser(description="Batch fetch job content")
    parser.add_argument("--limit", type=int, default=0, help="Max jobs to process (0 = all)")
    parser.add_argument("--overwrite", action="store_true", help="Re-fetch even if already fetched")
    parser.add_argument("--llm", action="store_true", help="Trigger LLM analysis after fetch")
    parser.add_argument("--delay", type=float, default=1.0, help="Delay between requests (seconds)")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    # Find jobs that need content
    engine = get_sync_engine()
    with Session(engine) as session:
        query = session.query(Job).filter(
            Job.url.isnot(None),
            Job.url != "",
        )

        if not args.overwrite:
            query = query.filter((Job.fetched_content.is_(None)) | (Job.fetched_content == ""))

        # Prioritise jobs with empty descriptions (they need content most)
        query = query.order_by(
            # Empty description first, then by discovered_at descending
            Job.description.asc().nullsfirst(),
            Job.discovered_at.desc().nullslast(),
        )

        if args.limit > 0:
            query = query.limit(args.limit)

        jobs = query.all()

    if not jobs:
        logger.info("No jobs need content fetching")
        return

    logger.info("Found %d jobs to fetch content for", len(jobs))

    fetched = 0
    failed = 0
    with httpx.Client() as client:
        for i, job in enumerate(jobs):
            if i > 0 and args.delay > 0:
                time.sleep(args.delay)

            sys.stdout.write(f"\r[{i + 1}/{len(jobs)}] {job.title[:50]:50s} ")
            sys.stdout.flush()

            ok = fetch_and_store(job, client, overwrite=args.overwrite)
            if ok:
                fetched += 1
                sys.stdout.write("✓")
            else:
                failed += 1
                sys.stdout.write("✗")
            sys.stdout.write("\n")

    logger.info("Done — %d fetched, %d failed/skipped", fetched, failed)


if __name__ == "__main__":
    main()
