# @job-engine-scrapers/scraper-upwork

Upwork Job Scraper — enhanced stealth Playwright scraper for upwork.com.

Searches Upwork's public search page for each tag, extracting visible
job listings without authentication.

## Usage

```js
const scraper = require("@job-engine-scrapers/scraper-upwork");
scraper.main().then(result => console.log(result));
```
