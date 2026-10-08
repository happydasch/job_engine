import json
import sys
from pathlib import Path

from job_engine.config import config
from job_engine.database import init_db_sync, save_jobs_sync


def main():
    input_path = Path(sys.argv[1]) if len(sys.argv) > 1 else config.all_json_path

    if not input_path.exists():
        print(f"❌ Input file not found: {input_path}")
        print("   Run scrapers first: node scrapers/run.js")
        sys.exit(1)

    # Load JSON
    with open(input_path) as f:
        jobs = json.load(f)

    print(f"📄 Loaded {len(jobs)} jobs from {input_path}")

    # Initialize DB
    engine = init_db_sync()
    print("🗄️  Database initialized")

    # Save to DB
    new_count = save_jobs_sync(jobs, engine=engine)
    total = len(jobs)

    print(f"✅ Saved {new_count} new / {total} total jobs to database")
    print(f"   DB: {config.database_url}")


if __name__ == "__main__":
    main()
