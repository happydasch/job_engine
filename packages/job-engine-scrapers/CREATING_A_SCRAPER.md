# Creating a Scraper — Step-by-Step Guide

This guide walks you through creating a new scraper for the Job Engine, from
scaffolding to shipping. It uses a **hypothetical** job board API called
"JobBoard.io" so the concepts stay clean and portable.

## Prerequisites

- Node.js 18+
- The repo is set up (`make install` works)
- You understand basic JavaScript and async/await

## Quick Start (5 minutes)

Use the scaffolding tool to generate a scraper stub:

```bash
cd packages/job-engine-scrapers
node create-scraper.mjs <id> --type <api|fetch|browser> --name "Display Name"
```

This creates `scrapers/<id>/` with `index.js`, `package.json`, `README.md`,
and `tests/scrapers/test-<id>.js`. Then fill in the `// TODO:` markers.

**The rest of this guide explains what each TODO means and how to fill it.**

---

## 1. Understand the Contract

Every scraper is a Node.js module that must export three things:

| Export | What it does |
|--------|-------------|
| `metadata` | Object with `id`, `name`, `capabilities`, `needsBrowser`, `configFields` |
| `main()` | Async function that scrapes, filters, and calls `writeOutput()` |
| `register(registry)` | Self-registration hook: `registry.register(this)` |

Each job must be a `JobOffer` object with these **required** fields:

| Field | Example |
|-------|---------|
| `external_id` | `justjoin_abc123` |
| `platform` | `justjoin.it` |
| `title` | `Senior Python Developer` |
| `company` | `Acme Corp` |
| `url` | `https://...` |

And **scoring-critical** fields that strongly affect match accuracy:

| Field | Why it matters |
|-------|---------------|
| `salary_min`, `salary_max` | Used for rate fit scoring |
| `currency` | Enables currency conversion |
| `skills` | Primary driver of skill overlap scoring |
| `remote` | Used for location fit scoring |
| `location` | City/region for hybrid preferences |
| `category` | Category fit (python, backend, data, ai) |
| `experience_level` | Seniority matching |
| `contract_type` | B2B, permanent, full_time, etc. |
| `description` | Full text for LLM analysis |

The full contract is documented in `core/scraper-interface.js` (JSDoc) and
[DEVELOPMENT.md](../DEVELOPMENT.md#scraper-output-contract--joboffer-fields).

---

## 2. Which Pattern to Choose?

| Pattern | When to use | Example in this repo |
|---------|-------------|---------------------|
| **`api`** | The site has a public JSON API | justjoin_it, nofluffjobs, remoteok |
| **`fetch`** | Site renders HTML server-side, no JS needed | jooble, olx |
| **`browser`** | Site requires JavaScript rendering or has anti-bot | indeed, linkedin, simplyhired |

**Rule of thumb:** Prefer `api` > `fetch` > `browser` in that order. API
scrapers are faster, more reliable, and produce richer data.

---

## 3. Tutorial: Building an API Scraper

Let's build a scraper for **JobBoard.io** — a fictional job board with a
public API. Our scraper ID will be `jobboard_io`, type `api`.

### 3a. Scaffold

```bash
cd packages/job-engine-scrapers
node create-scraper.mjs jobboard_io --type api --name "JobBoard.io"
```

This creates:

```
scrapers/jobboard_io/
├── index.js         # Main scraper code (with TODOs)
├── package.json     # Package manifest
└── README.md        # Documentation
tests/scrapers/
└── test-jobboard_io.js  # Module structure test
```

### 3b. Understanding the Generated Code

Open `scrapers/jobboard_io/index.js`. The scaffolding gives you:

```
Imports from @job-engine-scrapers/core     ← Ready to use
Config loading (TAGS, TAG_SET, etc.)       ← Ready to use
fetchPage(pageNum)                         ← TODO: fill in API URL + pagination
isMatch(item)                              ← TODO: adjust field names
parseItem(item)                            ← TODO: map API fields to JobOffer
main()                                     ← Ready to use (orchestrates everything)
module.exports                             ← Ready to use (metadata, main, register)
```

### 3c. Fill in the API Endpoint

Let's say JobBoard.io has this API:

```
GET https://api.jobboard.io/v1/jobs?page=1&per_page=20
→ { "data": [ { "id": 123, "title": "...", "company": { "name": "..." }, ... } ] }
```

In `fetchPage()`, change:

```js
// Before (TODO):
const BASE_URL = "https://api.jobboard.io";
const url = `${BASE_URL}/jobs?page=${pageNum}`;
const items = body.data ?? body.results ?? body.jobs ?? body.offers ?? [];

// After:
const url = `https://api.jobboard.io/v1/jobs?page=${pageNum}&per_page=20`;
const items = body.data ?? [];
```

### 3d. Adjust Tag Matching

JobBoard.io returns skills as an array of strings in `item.skills`, so the
default `isMatch()` works. But if skills were nested under `item.skills_list`,
you'd change:

```js
const skills = (item.skills_list ?? []).map((s) => s.toLowerCase());
```

### 3e. Map API Fields to JobOffer

In `parseItem()`, map the actual API response shape. JobBoard.io returns:

```json
{
  "id": 123,
  "title": "Senior Python Developer",
  "company": { "name": "Acme Corp", "url": "https://acme.com" },
  "salary": { "min": 100000, "max": 150000, "currency": "USD" },
  "location": { "city": "San Francisco", "remote": true },
  "skills": ["python", "django", "postgresql"],
  "seniority": "senior",
  "description": "We are looking for...",
  "published_at": "2025-01-15T00:00:00Z"
}
```

Your `parseItem()` becomes:

```js
function parseItem(item) {
  return {
    external_id: `jobboard_${stableId(item.id)}`,
    platform: "JobBoard.io",
    title: item.title ?? "Unknown",
    company: item.company?.name ?? "Unknown",
    url: `https://jobboard.io/jobs/${item.id}`,
    salary_min: item.salary?.min ?? null,
    salary_max: item.salary?.max ?? null,
    currency: item.salary?.currency ?? "USD",
    contract_type: "full_time",
    location: item.location?.city ?? "Remote",
    remote: item.location?.remote ?? false,
    skills: (item.skills ?? []).map((s) => s.toLowerCase()),
    category: "",
    experience_level: item.seniority ?? "",
    requirements: item.description ?? "",
    discovered_at: new Date().toISOString(),
    nice_to_have_skills: "[]",
    languages: "[]",
    published_at: item.published_at ?? null,
    expired_at: null,
    working_time: "full_time",
    latitude: null,
    longitude: null,
    street: "",
    _raw: item._raw ?? [],
  };
}
```

### 3f. Test the Module Structure

```bash
cd packages/job-engine-scrapers
npm test -- --test-name-pattern "jobboard_io"
```

This runs `tests/scrapers/test-jobboard_io.js` which verifies the module
exports the correct metadata, main, and register.

### 3g. Enable and Run

Add to `data/scraper_config.yaml`:

```yaml
scrapers:
  jobboard_io:
    enabled: true
    max_pages: 5
```

Now install the scraper (creates the active wrapper the registry needs):

```bash
cd packages/job-engine-scrapers
node install-scraper.js jobboard_io
```

Test it standalone:

```bash
node -e "require('./scrapers/jobboard_io').main().then(r => console.log('Done:', r.count, 'jobs'))"
```

Or run with all scrapers:

```bash
node run.js
```

> **Why the install step?** The scraper registry only discovers scrapers from
> `data/active-scrapers/<id>/` — not from the source directory directly.
> `install-scraper.js` creates a thin wrapper there that re-exports your source
> code. The source directory itself is never modified.

---

## 4. Fetch (HTML) Scraper Tips

For sites that serve HTML without JavaScript, the `fetch` template gives you:

- `fetchHtml(url)` — fetches the page with proxy rotation + retry
- `parseJobsFromHtml(html, tag)` — a `// TODO:` where you use cheerio or regex
- `saveRawData()` — stores raw HTML for debugging

**Cheerio is available** (installed at the workspace level). Example:

```js
const cheerio = require("cheerio");

function parseJobsFromHtml(html, tag) {
  const $ = cheerio.load(html);
  const jobs = [];
  $(".job-listing, .job-card, .posting").each((i, el) => {
    jobs.push({
      title: $(el).find(".title, h2").text().trim(),
      company: $(el).find(".company, .employer").text().trim(),
      url: $(el).find("a[href*='/job/']").attr("href") ?? "",
      location: $(el).find(".location, .city").text().trim(),
      salary: $(el).find(".salary, .compensation").text().trim(),
      text: $(el).text().slice(0, 1200),
    });
  });
  return jobs;
}
```

---

## 5. Browser Scraper Tips

For JavaScript-rendered sites, the `browser` template gives you:

- `createStealthBrowser()` — Playwright with 15+ fingerprint evasion techniques
- `humanDelay()`, `humanScroll()` — human-like interaction patterns
- WAF detection (checks for Cloudflare, 403 pages)
- `parseSalary()` — handles common text formats (`$50k - $100k`, hourly rates)

**Key things to customize:**

1. **URL structure** — how the site's search URLs work
2. **Card selectors** — what CSS selectors match job cards in the DOM
3. **Field extraction** — how to extract title, company, salary, location from each card
4. **Pagination** — how to navigate to the next page (URL param, click, infinite scroll)

**Debugging tips:**

- Set `headless: false` to see what the browser is doing
- The template saves raw HTML via `saveRawData()` — inspect it to find selectors
- Check for WAF blocking by looking at saved HTML content

---

## 6. Validation Checklist

Before submitting your scraper, run through these checks:

- [ ] `npm test -- --test-name-pattern "<your_id>"` passes
- [ ] All `// TODO:` markers have been addressed
- [ ] `external_id` is unique per job (uses `stableId()` or a real platform ID)
- [ ] `salary_min` and `salary_max` are numbers (not strings)
- [ ] `skills` is an array of lowercase strings
- [ ] `remote` is a boolean
- [ ] The scraper handles errors gracefully (network failure, empty results, WAF)
- [ ] `saveRawData()` is called for at least one page (for debugging)
- [ ] The scraper has been tested with a real API/site request
- [ ] Tests pass: `cd packages/job-engine-scrapers && npm test`

---

## 7. Field Coverage Targets

Aim for this field coverage. Required fields are mandatory; scoring-critical
fields strongly recommended; optional fields are nice-to-have.

| Priority | Fields | Target |
|----------|--------|--------|
| **Required** | `external_id`, `platform`, `title`, `company`, `url` | 100% |
| **Scoring** | `salary_min`, `salary_max`, `currency`, `skills`, `remote`, `location`, `category`, `experience_level`, `contract_type`, `description` | API: 100%, Fetch: 70%, Browser: 80% |
| **Optional** | `nice_to_have_skills`, `languages`, `published_at`, `working_time` | API: 80%, Fetch: 30%, Browser: 30% |

See the [Field Coverage Matrix](DEVELOPMENT.md#per-scraper-field-coverage-matrix)
in DEVELOPMENT.md to see how existing scrapers compare.

---

## 8. Architecture Recap

```
scrapers/<id>/index.js     ← Your scraper code (this is what you create)
       ↓ call writeOutput()
data/scraper-output/<id>.json   ← Per-scraper output
data/scraper-output/_all.json   ← Merged, sorted output
       ↓ seed.py
data/job_engine.db              ← SQLite database
       ↓ served by
Dashboard (FastAPI + Vue 3 SPA) ← http://localhost:8000
```

The scraper never talks to the database directly — it writes JSON, and
`seed.py` loads it into the DB. This keeps scrapers simple and decoupled.