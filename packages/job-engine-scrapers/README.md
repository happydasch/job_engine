# Scrapers — Job Platform Scrapers

Node.js scraper framework. Scrapers are **packages** distributed through
**scraper catalogs**, installed into an **active set**, and discovered at runtime
by a self-registering **registry**.

## Architecture

```text
packages/job-engine-scrapers/
├── core/                    # @job-engine-scrapers/core — shared utilities
│   ├── registry.js          #   ScraperRegistry singleton
│   ├── scraper-interface.js #   JSDoc types + validateJobOffer()
│   ├── catalog.js            #   Catalog config + catalog queries
│   ├── config.js            #   Scraper config + profile tags
│   └── fetch/output/dedup/… #   Shared helpers
├── scrapers/                # Bundled scraper packages (the default local catalog)
│   └── <id>/                #   One package per scraper
│       ├── package.json     #   @job-engine-scrapers/scraper-<id>
│       ├── index.js         #   metadata + main() + register()
│       └── README.md
├── index.js                 # Discovery barrel — registers ACTIVE scrapers only
├── run.js                   # Orchestrator (parallel subprocess runner)
├── install-scraper.js       # Catalog CLI — install/uninstall/list/search
└── dump-metadata.js         # Dump registry metadata as JSON (used by Python)

data/
├── scraper_catalogs.yaml      # Catalog sources (auto-seeded on first run)
├── scraper_config.yaml      # Per-scraper enabled state + settings
└── active-scrapers/<id>/    # Installed scrapers (wrappers re-exporting the source)
```

The pipeline: **catalog** (where packages come from) → **install** (creates an
active wrapper in `data/active-scrapers/<id>/`) → **discovery** (`index.js`
registers only active scrapers) → **run** (`run.js` runs the ones enabled in
`data/scraper_config.yaml`).

Source packages are never modified by install/uninstall — the active wrapper
just re-exports them.

## Scraper Catalogs

Catalogs are the **only** source of the scraper catalog. There is **no fallback
catalog**: if `data/scraper_catalogs.yaml` lists no catalogs (or all catalogs return
nothing), the catalog is empty and nothing can be installed.

Config lives in `data/scraper_catalogs.yaml`, auto-seeded on first run. The default config registers the
bundled scrapers directory as a local catalog:

```yaml
catalogs:
  - id: bundled
    name: Bundled Scrapers
    type: local
    enabled: true
    path: packages/job-engine-scrapers/scrapers
```

Three catalog types:

| Type | Fields | Behavior |
| ---- | ------ | -------- |
| `local` | `path` | Scans the directory for subdirs containing a `package.json`. Relative paths resolve against the project root. |
| `npm` | `scope`, `registry` | Queries the registry search API for packages named `<scope>/scraper-<id>`. |
| `git` | `url`, `ref` | Installed via `npm install git+<url>` (not listable in the catalog). |

When several catalogs serve the same scraper ID, the first enabled catalog in the
list wins.

Manage catalogs from the CLI (or the dashboard, Scrapers → Catalog → sources):

```bash
node install-scraper.js --catalog list
node install-scraper.js --catalog add my-scrapers "My Scrapers" local
node install-scraper.js --catalog remove my-scrapers
```

`--catalog add` creates the entry; set type-specific fields (`path`, `scope`, …)
by editing `data/scraper_catalogs.yaml` or via the dashboard.

## Installing Scrapers

```bash
node install-scraper.js --list             # catalog with install status
node install-scraper.js --search crypto    # search by name/description/category
node install-scraper.js justjoin_it        # install
node install-scraper.js justjoin_it --catalog bundled   # install from a specific catalog
node install-scraper.js --installed        # list installed
node install-scraper.js --uninstall justjoin_it       # uninstall (source kept)
```

Or from the repo root: `make scraper-install ID=justjoin_it` /
`make scraper-uninstall ID=justjoin_it`. The dashboard's Scrapers → Catalog tab
does the same via the API.

Installing a `local`-catalog scraper creates `data/active-scrapers/<id>/` with an
`index.js` that re-exports the source package. Uninstalling removes only that
wrapper.

## Creating a New Scraper

Use the scaffolding tool to generate a complete scraper package:

```bash
node create-scraper.mjs <id> --type <api|fetch|browser> [--name "Display Name"]
```

| Type | When to use |
|------|-------------|
| `api` | Site has a public JSON API (richest data, easiest to maintain) |
| `fetch` | Site renders HTML server-side, no JavaScript (cheerio parsing) |
| `browser` | Site requires JavaScript or has anti-bot (Playwright stealth) |

### Example

```bash
# Scaffold
node create-scraper.mjs mynewjob --type api --name "MyNewJob"
```

Or from the repo root:

```bash
make create-scraper ID=mynewjob TYPE=api NAME="MyNewJob"
```

This creates `scrapers/mynewjob/` with `index.js`, `package.json`, `README.md`,
and `tests/scrapers/test-mynewjob.js`. Fill in the `// TODO:` markers for
site-specific logic (URLs, selectors, field mappings), then:

```bash
# 1. Run module structure validation
cd packages/job-engine-scrapers && npm test -- --test-name-pattern "mynewjob"

# 2. Install (creates the active wrapper the registry needs)
node install-scraper.js mynewjob

# 3. Enable in data/scraper_config.yaml
#     scrapers:
#       mynewjob:
#         enabled: true
#         max_pages: 5

# 4. Run with all scrapers
node run.js
```

📖 **Full guide:** See [CREATING_A_SCRAPER.md](CREATING_A_SCRAPER.md) for a
step-by-step tutorial covering all three patterns, the JobOffer contract,
validation checklist, and field coverage targets.

## Interface Contract

Every scraper module must export:

| Field | Type | Required | Description |
| ----- | ---- | -------- | ----------- |
| `metadata.id` | `string` | ✅ | Scraper ID (matches `scraper_config.yaml` key) |
| `metadata.name` | `string` | ✅ | Human-readable display name |
| `metadata.capabilities` | `string[]` | ✅ | `"browser"`, `"api"`, `"fetch"`, `"rss"` |
| `metadata.needsBrowser` | `boolean` | ✅ | Whether Playwright is required |
| `metadata.configFields` | `object` | — | Dashboard-editable settings schema |
| `main` | `function` | ✅ | Async scrape function |
| `register` | `function` | ✅ | Calls `registry.register(this)` |

## Job Offer Schema

Each scraper returns `{ platform, count, jobs }` where each job is:

| Field | Type | Required | Description |
| ----- | ---- | -------- | ----------- |
| `external_id` | `string` | Required | Unique job ID |
| `platform` | `string` | Required | Source site slug, e.g. `justjoin.it` |
| `title` | `string` | Required | Job title |
| `company` | `string` | Required | Company name |
| `url` | `string` | Required | Job listing URL |
| `salary_min` | `number\|null` | Scoring | Minimum salary |
| `salary_max` | `number\|null` | Scoring | Maximum salary |
| `currency` | `string` | Scoring | Currency (PLN, EUR, USD) |
| `contract_type` | `string` | Scoring | e.g. "b2b", "permanent" |
| `location` | `string` | Scoring | City or "Remote" |
| `remote` | `boolean` | Scoring | Remote-friendly |
| `skills` | `string[]` | Scoring | Skills/tags |
| `category` | `string` | Scoring | e.g. "python", "backend" |
| `experience_level` | `string` | Scoring | e.g. "mid", "senior" |
| `description` | `string` | Scoring | Full job description |
| `discovered_at` | `string` | Scoring | ISO timestamp |

**Required** = job is dropped by `writeOutput()` if missing/empty.
**Scoring** = strongly recommended; missing values degrade match scores but do not cause the job to be dropped.

Use `validateJobOffer(job, source)` from
`@job-engine-scrapers/core`.`scraperInterface` in your scraper.

## Debugging

```bash
node dump-metadata.js                  # JSON metadata of all REGISTERED (active) scrapers
node install-scraper.js --installed    # what's installed
node install-scraper.js --catalog list   # configured catalogs
node data/active-scrapers/<id>/index.js   # run one scraper directly (from repo root)
```

Common gotchas:

- **Scraper not in catalog** → its catalog is missing/disabled in
  `data/scraper_catalogs.yaml`, or the package dir has no `package.json`.
  There is no fallback catalog.
- **In catalog but not registered** → it's not installed. Only
  `data/active-scrapers/` is discovered; source packages are never
  auto-registered.
- **Registered but not running** → disabled in `data/scraper_config.yaml`.
