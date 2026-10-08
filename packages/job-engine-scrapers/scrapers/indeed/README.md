# @job-engine-scrapers/scraper-indeed

Indeed Scraper — browser-based Playwright scraper for indeed.com.

Searches Indeed for each search tag, extracts job listings from the
JavaScript-rendered DOM, and filters for matching tags.

## Features

- **Country-aware subdomain selection** — configure `country: pl` in scraper_config.yaml
  to use `pl.indeed.com` with Polish locale, timezone, and Accept-Language headers
- **Cloudflare/WAF detection** with fingerprint rotation retry
- **Resource blocking** — images, fonts, and media are blocked for speed + stealth
- **Locale matching** — browser locale, timezone, and language match the target country

## Usage

```js
const scraper = require("@job-engine-scrapers/scraper-indeed");
scraper.main().then(result => console.log(result));
```

## Environment

- `INDEED_COOKIE` — optional JSON cookie array to bypass Cloudflare
- `INDEED_DEBUG` — set `"1"` to save screenshots on failure for debugging

Proxy is handled via the shared system (`HTTP_PROXY`/`PROXY_SOURCES` in `.env`).

## Config

In `data/scraper_config.yaml`:

```yaml
indeed:
  enabled: true
  max_pages: 3
  country: pl  # Two-letter country code (us, pl, de, uk, fr, es, nl, it, jp, au, ca, in)
```

The `country` field controls:
- Indeed subdomain (e.g. `pl.indeed.com`)
- Browser locale (`pl-PL`)
- Browser timezone (`Europe/Warsaw`)
- `navigator.languages` order
- `Accept-Language` HTTP header
