# Evaluate Job Workflow

> **Purpose:** Browse scored job listings, understand match breakdowns across 8 scoring dimensions, and drill into individual job details.

## Layer Overview

```mermaid
flowchart LR
    CLI[make score] --> SCORER[skill_scorer.py]
    SCORER --> JSON[data/scraper-output/_all.json]
    PROFILE[data/my_profile.yaml] --> SCORER
    SCORER --> CLI_OUT[Top 10 CLI Printout]
    DASH[/jobs page] --> API[/api/jobs]
    API --> DB[(job_engine.db)]
    DB --> API
    API --> VUE[JobsView.vue / JobDetailView.vue]
```

## Step-by-Step

### 1. Score Jobs via CLI

```bash
make score
```

This runs:
```bash
python -m job_engine.skill_scorer data/scraper-output/_all.json --top 10
```

Prints the top 10 matching jobs ranked by overall score, with per-dimension breakdowns and highlighted matches.

### 2. The 8 Scoring Dimensions

Defined in `packages/job-engine-core/src/job_engine/skill_scorer.py`:

| Dimension | Weight | What It Measures |
|-----------|--------|-----------------|
| `skill_overlap` | **25%** | Profile skills present in job requirements. Critical skills (backend, databases, domain) get +5 bonus each, capped at +20 |
| `keyword_boost` | **15%** | Domain keyword matches (trading, fintech, ML, AI, etc.) from `boosted_keywords` in profile |
| `career_alignment` | **15%** | Long-term trajectory fit — how well the job aligns with `career_goals` from the profile |
| `behavioral_fit` | **13%** | Culture keywords (remote_first, async_communication, ownership, etc.) matched against job description |
| `rate_fit` | **12%** | Salary range vs `rate.min_monthly` / `rate.max_monthly` from profile. Supports multi-currency via `currency_converter.py` |
| `location_fit` | **8%** | Remote / hybrid / city match against `preferred_locations` and `remote_only` preference |
| `category_fit` | **8%** | Job category alignment with profile skill categories |
| `experience_fit` | **4%** | Seniority level match — `experience_years` from profile vs job's `experience_level` |

Weights sum to **1.0** (100%). The final score is `sum(weight * dimension_score)` normalized to 0–100.

### 3. Dashboard: Browse & Filter Jobs

Navigate to **`http://localhost:8000/jobs`**:

- **Job list:** Sortable, paginated `DataTable` with columns: Title, Company, Platform, Location, Rate, Score
- **Filters sidebar:** FilterPanel with:
  - Platform toggle groups (justjoin.it, linkedin, nofluffjobs, etc.)
  - Skill tags
  - Category select
  - Remote toggle
- **Sort:** Click any column header to sort ascending/descending
- **Search:** Type in the search box to filter by title or company

### 4. Dashboard: Job Detail View

Click any job → **`/jobs/{id}`**:

| Section | Shows |
|---------|-------|
| **Header** | Job title, company, platform badge, remote badge |
| **Match Score Ring** | `ScoreBadge.vue` — overall score as a ring/pill with color (green >70, yellow 50–70, red <50) |
| **Match Breakdown** | Per-dimension bars showing each dimension's contribution (0–100) |
| **Job Details** | Full description, skills list, salary range, location |
| **Actions** | Favorite/Hide buttons (`JobFavHideButtons.vue`), "Fetch Content" button |
| **LLM Analysis** | Tabs for: Analysis, Match Explanation, Cover Letter, Interview Questions |

### API Endpoints

| Method | Endpoint | Purpose |
|--------|----------|---------|
| `GET` | `/api/jobs` | Scored, filtered, paginated job list |
| `GET` | `/api/jobs/{id}` | Single job detail with match breakdown |
| `GET` | `/api/jobs/fields` | Filter enums (platforms, skills, categories) |
| `PATCH` | `/api/jobs/{id}/toggle-fav` | Toggle favorite |
| `PATCH` | `/api/jobs/{id}/toggle-hide` | Toggle hidden |

Each job returned by `/api/jobs` includes a `match_breakdown` object with per-dimension scores and an overall `score` (0–100).

### Data Model

**`Job`** (SQLAlchemy model in `packages/job-engine-core/src/job_engine/models.py`):

| Field | Type | Description |
|-------|------|-------------|
| `id` | PK | Auto-increment |
| `external_id` | String(255), unique | Platform ID e.g. `justjoin_<guid>` |
| `platform` | String(50) | Source platform |
| `title` | String(255) | Job title |
| `company_id` | FK → companies | Normalized company |
| `url` | Text | Offer URL |
| `description` | Text | Job description |
| `salary_min` / `salary_max` | Float | Salary range |
| `currency` | String(10) | Currency code |
| `skills` | Text (JSON) | List of required skills |
| `category` | String(100) | Job category |
| `experience_level` | String(50) | Seniority level |
| `remote` / `hybrid` | Boolean | Work mode flags |
| `location` / `city` | String | Location info |
| `status` | String(20) | new, applied, etc. |
| `score` | Float | Overall match score |
| `match_breakdown` | Text (JSON) | Per-dimension scores |

### Layer Trace

| Layer | File | Key Code |
|-------|------|----------|
| **DB** | `packages/job-engine-core/src/job_engine/models.py` | `Job` model, `Company` model |
| **Core** | `packages/job-engine-core/src/job_engine/skill_scorer.py` | `JobMatcher`, `WEIGHTS`, `score()`, `score_detail()` |
| **API** | `packages/job-engine-dashboard/src/dashboard/routes/jobs.py` | `api_jobs()`, `api_job_detail()` |
| **Composable** | `packages/job-engine-dashboard/src/composables/useJobFilters.js` | Filter state + query building |
| **Component** | `packages/job-engine-dashboard/src/views/JobsView.vue` | Job list with filters |
| **Component** | `packages/job-engine-dashboard/src/views/JobDetailView.vue` | Detail view with match breakdown |

### Key Files

| File | Purpose |
|------|---------|
| `packages/job-engine-core/src/job_engine/skill_scorer.py` | `JobMatcher` class, `WEIGHTS` dict, `score_all_jobs()` entry point |
| `packages/job-engine-core/src/job_engine/skill_gap.py` | Skill gap analysis (what skills are missing for a given role) |
| `packages/job-engine-core/src/job_engine/currency_converter.py` | `convert()` — cross-currency salary normalization |
| `packages/job-engine-dashboard/src/composables/useJobFilters.js` | Job-specific filter composable |
| `packages/job-engine-dashboard/src/components/common/ScoreBadge.vue` | Score ring/pill display |