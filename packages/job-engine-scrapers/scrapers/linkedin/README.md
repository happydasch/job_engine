# @job-engine-scrapers/scraper-linkedin

LinkedIn Jobs scraper — uses the public guest job-search API
(`/jobs-guest/jobs/api/seeMoreJobPostings/search`) to scrape job listings without
requiring a login. No session cookie is needed for the guest API.

Searches for boosted keywords from the profile, extracts job listings from
server-rendered HTML fragments, and filters for matching tags.

All configuration comes from `data/scraper_config.yaml` (no env vars).

## Usage

```js
const scraper = require("@job-engine-scrapers/scraper-linkedin");
scraper.main().then(result => console.log(result));
```

## Config (data/scraper_config.yaml)

```yaml
linkedin:
  enabled: true
  max_pages: 1               # pages of 10 cards each (default: 2)
  location: "Poland"         # location filter; empty = worldwide
  seconds_since_posted: 604800  # freshness filter (7 days); 0 = any
  request_delay_ms: 5000     # delay between requests to avoid 429
  cookie: ""                 # optional: JSON array of cookie objects
  debug: false               # set true to save screenshots + raw HTML
```

## Config Fields

Configured via the dashboard at `/scrapers` or directly in `scraper_config.yaml`:

| Field | Type | Description |
|-------|------|-------------|
| `max_pages` | number | Max pages of 10 cards each |
| `location` | string | Location filter (e.g. "Poland"). Empty = worldwide |
| `seconds_since_posted` | number | Freshness filter in seconds (604800 = 7d). 0 = any |
| `request_delay_ms` | number | Delay between requests to avoid rate limiting |
| `cookie` | password | Session cookie JSON array (optional, raises guest rate limit) |
| `debug` | boolean | Save screenshots/raw HTML for debugging |
