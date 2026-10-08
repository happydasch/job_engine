# @job-engine-scrapers/scraper-googlejobs

Google Jobs Scraper — experimental browser-based Playwright scraper for Google Jobs.

Searches Google's Jobs tab for each search tag. Google aggressively blocks
automated traffic, so this scraper is experimental and may need manual
session cookies or additional stealth measures.

## Usage

```js
const scraper = require("@job-engine-scrapers/scraper-googlejobs");
scraper.main().then(result => console.log(result));
```

## Environment

- `GOOGLE_JOBS_COOKIE` — optional cookie string for authenticated search
