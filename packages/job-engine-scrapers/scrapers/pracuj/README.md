# @job-engine-scrapers/scraper-pracuj

Pracuj.pl Scraper — browser-based Playwright scraper with detail-page enrichment.

Two-phase approach: listing page scraping via Playwright, then concurrent
detail-page enrichment for skills, descriptions, and JSON-LD structured data.

## Usage

```js
const scraper = require("@job-engine-scrapers/scraper-pracuj");
scraper.main().then(result => console.log(result));
```

## Environment

- `PRACUJ_DETAIL_CONCURRENCY` — number of concurrent detail page workers (default: 3)
- `PRACUJ_DELAY_MS` — delay between detail page requests (default: 1500)
