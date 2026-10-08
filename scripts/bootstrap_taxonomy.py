"""Bootstrap the taxonomy registry from built-in alias maps and existing data.

Usage:
    python scripts/bootstrap_taxonomy.py

This script:
1. Seeds the taxonomy registry from SEED_ALIASES (built-in)
2. Scans all existing jobs for unique skill strings
3. Scans the profile for boosted_keywords, behavioral_keywords, career_goals
4. Outputs a summary of terms created
"""

import json
import logging
import sys
from pathlib import Path

from sqlalchemy import select, text
from sqlalchemy.orm import Session

# Ensure job_engine is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from job_engine.database import get_sync_engine, init_db_sync
from job_engine.models import Job, TaxonomySynonym, TaxonomyTerm
from job_engine.taxonomy import (
    TaxonomyResolver,
    _canonicalize_variant,
    seed_taxonomy_from_builtins,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("bootstrap_taxonomy")


def bootstrap_taxonomy():
    """Run the full taxonomy bootstrap."""
    engine = get_sync_engine()
    init_db_sync(engine)

    with Session(engine) as session:
        # Phase 1: Seed from built-in aliases
        logger.info("Seeding taxonomy from built-in aliases...")
        created = seed_taxonomy_from_builtins(session)
        logger.info("  Created %d new taxonomy terms", created)

        # Phase 2: Scan all existing jobs for unique skill strings
        resolver = TaxonomyResolver(session)
        logger.info("Scanning existing jobs for skills...")
        jobs = session.execute(select(Job)).scalars().all()

        total_skills = 0
        new_skills = 0
        for job in jobs:
            try:
                skills = json.loads(job.skills) if job.skills else []
            except (json.JSONDecodeError, TypeError):
                continue
            for skill in skills:
                if not isinstance(skill, str) or not skill.strip():
                    continue
                total_skills += 1
                slug = resolver.resolve(skill, "skill")
                if slug == _canonicalize_variant(skill):
                    new_skills += 1

            # Also scan nice_to_have_skills
            try:
                nice_skills = json.loads(job.nice_to_have_skills) if job.nice_to_have_skills else []
            except (json.JSONDecodeError, TypeError):
                continue
            for skill in nice_skills:
                if not isinstance(skill, str) or not skill.strip():
                    continue
                total_skills += 1
                slug = resolver.resolve(skill, "skill")

        session.commit()
        logger.info(
            "  Scanned %d jobs, %d skill occurrences, %d auto-registered",
            len(jobs),
            total_skills,
            new_skills,
        )

        # Phase 3: Seed category terms from scraper config / job categories
        logger.info("Scanning job categories...")
        cat_result = session.execute(
            text("SELECT DISTINCT category FROM jobs WHERE category != '' AND category IS NOT NULL")
        ).all()
        cat_count = 0
        for row in cat_result:
            cat = row[0].strip().lower()
            if cat and cat not in ("n/a", "?"):
                resolver.resolve(cat, "category")
                cat_count += 1
        session.commit()
        logger.info("  Registered %d job categories", cat_count)

    # Print summary
    with Session(engine) as session:
        term_count = session.execute(select(TaxonomyTerm)).scalars().all()
        syn_count = session.execute(select(TaxonomySynonym)).scalars().all()
        print(f"\n{'=' * 50}")
        print("  Taxonomy Bootstrap Complete")
        print(f"  Terms:     {len(term_count)}")
        print(f"  Synonyms:  {len(syn_count)}")
        print(f"{'=' * 50}\n")

    return len(term_count)


if __name__ == "__main__":
    bootstrap_taxonomy()
