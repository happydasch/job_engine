# @job-engine-scrapers/scraper-simplyhired

SimplyHired Scraper — browser-based Playwright scraper for simplyhired.com.

Searches SimplyHired for each search tag, extracts job listings from the
JavaScript-rendered DOM, and filters for matching tags.

## Usage

```js
const scraper = require("@job-engine-scrapers/scraper-simplyhired");
scraper.main().then(result => console.log(result));
```
