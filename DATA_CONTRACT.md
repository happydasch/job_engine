# DATA_CONTRACT.md — System/User File Boundary

> **Effective:** This document defines which files in the repository are considered `USER_LAYER` (user-managed, never auto-modified) vs `SYSTEM_LAYER` (system-managed, safe to auto-update). Agents **must not** modify `USER_LAYER` files without explicit confirmation.

## Classification

| Layer | Definition | Examples |
|-------|-----------|----------|
| `USER_LAYER` | User-managed configuration and data files. **Never auto-modified** by agents without explicit confirmation. | `data/my_profile.yaml`, `data/scraper_config.yaml`, `config/.env` |
| `SYSTEM_LAYER` | System-managed source code, configuration templates, and documentation. **Safe to auto-update** during development. | `packages/`, `scripts/`, `Makefile`, `pyproject.toml` |
| `UNDEFINED` | Runtime data that is neither user-authored nor system code. Agents may read/write as needed for operation. | `data/job_engine.db`, `data/scraper-output/`, `data/active-scrapers/` |

## USER_LAYER — Full File List

The following files are **never modified** without explicit confirmation:

- `data/my_profile.yaml` — User skills, rate, preferences, career goals
- `data/scraper_config.yaml` — Scraper platform settings (enabled, pagination)
- `data/app_settings.yaml` — Application settings (LLM config, language, research depth)
- `data/exchange_rates.json` — Cached currency exchange rates
- `data/scraper_catalogs.yaml` — Scraper catalog registry
- `data/my_cv.md` — Canonical CV in markdown (user must provide)
- `data/my_style.md` — Writing style preferences (user must provide)
- `data/my_rules.md` — Procedural rules for LLM generation (user must provide)
- `config/.env` — Environment variables (secrets, paths)

## SYSTEM_LAYER — Full File List

The following files are **safe to auto-update** during development:

**Configuration Templates:**
- `config/.env.example` — Environment template
- `config/.env.ci` — CI environment template
- `examples/my_profile.example.yaml` — Profile template
- `config/my_cv.example.md` — CV template
- `config/my_style.example.md` — Style template
- `config/my_rules.example.md` — Rules template
- `config/scraper_catalogs.yaml` — Catalog source template

**Source Code:**
- `packages/job-engine-core/src/job_engine/` — Python core package
- `packages/job-engine-dashboard/` — FastAPI + Vue 3 SPA
- `packages/job-engine-scrapers/` — Node.js scraper framework

**Scripts:**
- `scripts/` — CLI entry points

**Build & Config:**
- `Makefile` — Task runner
- `pyproject.toml` — Root project metadata
- `requirements.txt` — Root deps
- `docker-compose.yml` — Docker compose
- `docker/` — Dockerfile components

**Documentation:**
- `README.md` — User-facing documentation
- `DEVELOPMENT.md` — Developer reference
- `AGENTS.md` — AI agent instruction file
- `DATA_CONTRACT.md` — This file
- `docs/` — Workflow documentation (user journeys)
- `DATA_CONTRACT.md` — System/User file boundary

**Root Files:**
- `VERSION` — Canonical version source
- `.gitignore`
- `.project-root` — Project root sentinel

## UNDEFINED — Runtime Data

The following files are not classified as either layer. Agents may read/write as needed:

- `data/job_engine.db` — SQLite database (runtime data)
- `data/scraper-output/` — Scraper JSON results and raw data (runtime data)
- `data/active-scrapers/` — Installed scraper packages (runtime data)
- `data/reports/` — Numbered LLM analysis reports (runtime data)
- `data/archives/` — Archived application materials (runtime data)
- `data/plugins/` — User-installed plugins (runtime data)
- `data/plugins.yml` — Plugin enable registry (runtime data)

## Rules for Agents

1. **Never modify USER_LAYER files** without asking the user for explicit confirmation.
2. **SYSTEM_LAYER files may be modified** during development tasks — this is the normal workflow.
3. **UNDEFINED files may be read/written** as needed for operation.
4. **When creating a new file**, classify it according to the rules above and add it to the appropriate list in this document.
5. **This document is SYSTEM_LAYER** — agents may update this document to reflect changes in file classification.