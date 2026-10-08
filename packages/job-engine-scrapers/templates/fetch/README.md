# {{displayName}} Scraper

TODO: Describe what {{displayName}} is, what it offers, and what data this scraper extracts.

**Type:** HTML fetch-based scraper
**Capabilities:** `fetch`
**Data Richness:** low
**Homepage:** TODO

## Usage

```js
const scraper = require("@job-engine-scrapers/scraper-{{kebabId}}");
scraper.main().then(result => console.log(result));
```

## Configuration

See `data/scraper_config.yaml` for per-scraper settings:

```yaml
scrapers:
  {{id}}:
    enabled: true
    max_pages: 5
```

## Data Extracted

- Job title, company, location
- Salary range (parsed from text)
- Skills extracted via regex (`extractSkills()`)
- Basic job metadata