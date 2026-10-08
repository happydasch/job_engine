<!--
  quickstart.md — Quick start, key commands, and scraper catalog for the Job Engine.
-->

# Quick Start

## Setup

```bash
cp config/.env.example config/.env
cp examples/my_profile.example.yaml data/my_profile.yaml    # <-- edit with your details
make install
make dashboard                                 # open http://localhost:8000
# In the Scrapers tab, click "Run All" to scrape enabled scrapers + seed the DB
make score                                     # print top matches in the terminal
```

## Key Commands

For the full key commands table with descriptions, see [Key Commands](../DEVELOPMENT.md#key-commands) in DEVELOPMENT.md, or run `make help`.

## Scraper Catalog

The Scraper Catalog at `/scrapers?tab=catalog` provides a browsable UI to browse, install, and uninstall scraper packages from the dashboard or CLI.

Each scraper package lives in `packages/job-engine-scrapers/scrapers/<id>/`. When installed, an **active wrapper** is created in `data/active-scrapers/<id>/` — the original source is NEVER modified.

The catalog is built **exclusively** from catalog sources defined in `data/scraper_catalogs.yaml` (auto-seeded on first run). Types: `local`, `npm`, `git`.

For detailed architecture, dashboard catalog tab features, full CLI commands, and per-scraper configuration, see the [Scraper Catalog](../DEVELOPMENT.md#scraper-catalog) section in DEVELOPMENT.md.

## Scraper Configuration Policy

All scraper configuration must come from `data/scraper_config.yaml` — **no environment variables.**

- Every configurable option must be declared in the scraper's `metadata.configFields` with a proper `type`, `label`, and `description`.
- The dashboard at `/scrapers` renders a config form from `configFields` and persists values back to the YAML file.
- **Password/secret fields** use `type: "password"` in `configFields` — the dashboard renders these as `<input type="password">`.
- Scrapers read their config via `config.getScraper(id)` which returns the full YAML block for that scraper.
- **Never use `process.env`** in a scraper module. If a value needs to be configurable, add it to `configFields` and read it from the scraper config block.