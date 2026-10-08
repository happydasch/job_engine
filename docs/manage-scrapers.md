# Manage Scrapers Workflow

> **Purpose:** Enable/disable individual scrapers, install new ones from the catalog, view run history, and configure per-scraper settings — all from the dashboard.

## Layer Overview

```mermaid
flowchart LR
    DASH[/scrapers page] --> CONFIG[data/scraper_config.yaml]
    DASH --> CATALOG[Scraper Catalog Tab]
    CATALOG --> INSTALL[install-scraper.js]
    INSTALL --> ACTIVE[data/active-scrapers/]
    DASH --> HISTORY[Run History]
    HISTORY --> DB[(job_engine.db)]
    DB --> LOG[ScraperLog Table]
    DASH --> RUN[Trigger Scrape]
    RUN --> TM[TaskManager]
    TM --> SRM[ScraperRunManager]
```

## Step-by-Step

### 1. Navigate to the Scrapers Dashboard

Go to **`http://localhost:8000/scrapers`** — the main scraper management page.

The page has two tabs rendered via `AppTabs.vue`:

| Tab | Content |
|-----|---------|
| **Scrapers** | Enable/disable, run, view per-scraper config |
| **Catalog** | Browse, install, and uninstall scraper packages |

### 2. Enable / Disable Scrapers

Each scraper is shown as a card with:

| Element | Description |
|---------|-------------|
| **Toggle** | Switch to enable/disable the scraper |
| **Status badge** | Shows last run status (success, failed, never run) |
| **Job count** | How many jobs were found in the last run |
| **Run button** | Trigger a single-scraper run |
| **Config button** | Edit per-scraper settings |

**Toggle flow:**

1. Click toggle → sends `PUT /api/scrape/scrapers/{id}` with `{"enabled": true/false}`
2. The backend persists to `data/scraper_config.yaml`
3. On next scrape run, `run.js` reads `scraper_config.yaml` via `config.js` — only enabled scrapers are executed

### 3. Per-Scraper Configuration

Scrapers may declare `configFields` in their metadata. These are rendered as a config form in the dashboard:

| Field Type | Dashboard Input |
|------------|-----------------|
| `string` | `<input type="text">` |
| `number` | `<input type="number">` |
| `boolean` | `<input type="checkbox">` |
| `password` | `<input type="password">` (hidden input) |
| `select` | `<select>` dropdown |

**API:** `PUT /api/scrape/scrapers/{id}/config` — saves config values to `data/scraper_config.yaml` under the scraper's `config` key.

Scrapers read their config via `config.getScraper(id)` in `packages/job-engine-scrapers/core/config.js`.

### 4. Run History

The Scrapers page shows a run history table with:

| Column | Description |
|--------|-------------|
| **Start Time** | When the run started |
| **Duration** | Elapsed time in seconds |
| **Status** | completed, failed, timed_out |
| **Jobs Found** | Total jobs discovered |
| **Jobs New** | New jobs seeded to DB |
| **Scrapers** | Count of completed / total scrapers |
| **Logs** | Click to view `GET /api/scrape/logs/{task_id}` |

**Data source:** `ScraperLog` table in SQLite (model in `packages/job-engine-core/src/job_engine/models.py`).

### 5. Scraper Catalog

The **Catalog** tab provides a browsable UI to discover and install scraper packages.

**Catalog sources** are defined in `data/scraper_catalogs.yaml` (seeded from `config/scraper_catalogs.yaml` template on first run):

| Type | Description | Example |
|------|-------------|---------|
| `local` | Local directory of scraper packages | `type: local, path: ./packages/job-engine-scrapers/scrapers` |
| `npm` | npm registry package | `type: npm, package: @job-engine/scraper-linkedin` |
| `git` | Git repository | `type: git, url: https://github.com/...` |

**Install from catalog:**

1. Browse available scrapers in the catalog list
2. Click "Install" on a scraper → sends `POST /api/scrapers/catalog/install/{id}`
3. Backend runs `node packages/job-engine-scrapers/install-scraper.js <id>`
4. Creates an active wrapper in `data/active-scrapers/<id>/`
5. The original source package is **never modified**

**Uninstall:** Click "Uninstall" → removes the active wrapper from `data/active-scrapers/`.

### 6. Schedule Configuration

The scraper page includes a schedule section:

```json
PUT /api/scrape/schedule
{
  "interval_minutes": 360,
  "enabled": true
}
```

When enabled, `ScraperRunManager` automatically runs scrapers every `interval_minutes` (default: 6 hours).

### API Endpoints

| Method | Endpoint | Purpose |
|--------|----------|---------|
| `GET` | `/api/scrape/scrapers` | List scrapers with enabled state |
| `PUT` | `/api/scrape/scrapers/{id}` | Toggle scraper enabled |
| `GET` | `/api/scrape/scrapers/{id}/config` | Get per-scraper config |
| `PUT` | `/api/scrape/scrapers/{id}/config` | Update per-scraper config |
| `GET` | `/api/scrape/schedule` | Get auto-run schedule |
| `PUT` | `/api/scrape/schedule` | Set auto-run schedule |
| `POST` | `/api/scrape` | Start all scrapers |
| `POST` | `/api/scrape/scraper/{id}` | Start single scraper |
| `GET` | `/api/scrape/status` | Current run status |
| `GET` | `/api/scrape/status/{task_id}` | Status by task ID |
| `GET` | `/api/scrape/history` | Run history |
| `GET` | `/api/scrape/logs/{task_id}` | Log lines for a run |
| `POST` | `/api/scrape/cancel/{task_id}` | Cancel a running run |
| `GET` | `/api/scrapers/catalog/list` | List catalog scrapers |
| `GET` | `/api/scrapers/catalog/search` | Search catalog |
| `POST` | `/api/scrapers/catalog/install/{id}` | Install scraper |
| `POST` | `/api/scrapers/catalog/uninstall/{id}` | Uninstall scraper |

### Config File: `data/scraper_config.yaml`

```yaml
scrapers:
  justjoin_it:
    enabled: true
    config:
      max_pages: 5
  linkedin:
    enabled: true
    config:
      max_pages: 3
  indeed:
    enabled: false
schedule:
  enabled: true
  interval_minutes: 360
```

### CLI Commands (alternatives)

```bash
# List available scrapers in the catalog
make scraper-catalog

# Install a scraper by ID
make scraper-install ID=my_scraper

# Uninstall a scraper
make scraper-uninstall ID=my_scraper

# Dump scraper metadata (for debugging)
make scraper-metadata
```

### Layer Trace

| Layer | File | Key Code |
|-------|------|----------|
| **Config** | `packages/job-engine-core/src/job_engine/scraper_config.py` | `get_scraper_config()`, `save_scraper_config()` |
| **Config** | `packages/job-engine-core/src/job_engine/scraper_catalog_config.py` | Catalog source management |
| **DB** | `packages/job-engine-core/src/job_engine/models.py` | `ScraperLog` model |
| **API** | `packages/job-engine-dashboard/src/dashboard/routes/scrapers.py` | All scraper CRUD endpoints |
| **API Helper** | `packages/job-engine-dashboard/src/dashboard/scraper_utils.py` | Status helpers |
| **Node.js** | `packages/job-engine-scrapers/core/config.js` | `config.getScraper(id)` |
| **Node.js** | `packages/job-engine-scrapers/install-scraper.js` | Install/uninstall logic |
| **Node.js** | `packages/job-engine-scrapers/core/catalogs.js` | Catalog source resolution |
| **Composable** | `packages/job-engine-dashboard/src/composables/useTaskPoll.js` | Poll run status |
| **Component** | `packages/job-engine-dashboard/src/views/ScrapersView.vue` | Full scraper management UI |

### Troubleshooting

| Symptom | Likely Cause |
|---------|-------------|
| Scraper toggle doesn't persist | `data/scraper_config.yaml` is read-only or permissions issue |
| Catalog shows no scrapers | Check `data/scraper_catalogs.yaml` exists and has sources defined |
| Install fails | npm registry unreachable or git URL invalid |
| Run history empty | No scrape runs have completed yet. Trigger a run first |
| Scraper config not saving | Ensure `configFields` are declared in the scraper's metadata |