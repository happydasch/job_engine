# {{displayName}} Scraper

TODO: Describe what {{displayName}} is, what it offers, and what anti-bot measures are in place.

**Type:** Browser-based Playwright scraper
**Capabilities:** `browser`
**Data Richness:** medium
**Homepage:** TODO

## Usage

```js
const scraper = require("@job-engine-scrapers/scraper-{{kebabId}}");
scraper.main().then(result => console.log(result));
```

## Requirements

Requires Playwright (installed at the workspace level). Ensure Playwright is installed:

```bash
cd packages/job-engine-scrapers && npx playwright install chromium
```

## Configuration

See `data/scraper_config.yaml` for per-scraper settings:

```yaml
scrapers:
  {{id}}:
    enabled: true
    max_pages: 3
```

## Data Extracted

- Job title, company, location
- Salary range parsed from DOM text
- Skills extracted via regex (`extractSkills()`)
- Remote status detection

## Anti-Bot Measures

- Stealth browser with fingerprint rotation
- Human-like delays and scrolling
- WAF detection and graceful failure
- Proxy support (optional)