# Arc.dev Scraper

Fetch-based scraper for [arc.dev/remote-jobs](https://arc.dev/remote-jobs).

## Strategy

Arc is a Next.js app that server-renders its job lists into the
`__NEXT_DATA__` JSON blob. No browser is needed — we `fetch` the HTML and parse
`props.pageProps`.

Two lists live in the payload:

| List | Detail URL | Data | Used? |
|------|------------|------|-------|
| `arcJobs[]` | `/remote-jobs/details/{urlString}-{randomKey}` → **200** | salary, experience, timezone, skills | ✅ |
| `externalJobs[]` | detail path **404s**, no source/apply URL in payload | limited | ❌ skipped |

`externalJobs` are aggregated third-party postings with no reachable Arc detail
page and no apply URL in the listing data, so they cannot be linked and are
skipped (the count is logged).

### Coverage

There is no client-side pagination API — the list is virtualized from the SSR
payload, so scrolling reveals nothing new over the network. To broaden coverage
the scraper fetches:

1. the base page `/remote-jobs` (newest across all roles), plus
2. one skill-category page `/remote-jobs/{slug}` per configured search term,
   where `slug` is the lowercased, hyphenated term (e.g. `TypeScript` →
   `typescript`).

Each page contributes up to ~20 exclusive jobs; results are deduped by
`randomKey`. Unknown category slugs simply redirect to the base page and add
nothing after dedup.

## Config

`data/scraper_config.yaml`:

```yaml
scrapers:
  arcdev:
    enabled: true
    max_categories: 20      # skill-category pages fetched on top of the base page
    request_delay_ms: 800   # politeness delay between requests
```

## Run standalone

```bash
node packages/job-engine-scrapers/scrapers/arcdev/index.js
```

## Field notes

- **Salary** — prefers `min/maxAnnualSalary`; falls back to
  `min/maxHourlyRate × 2080`. Currency is USD.
- **Company** — Arc withholds exclusive-client names in listing data, so
  `company` is `"Unknown"`.
- **contract_type** — `contract`/`freelance` → `B2B`, `permanent` → `Permanent`.
- **experience_level** — passed through from Arc (`mid`, `senior`, …).
- **location** — `requiredCountries` joined, else `Remote`.
