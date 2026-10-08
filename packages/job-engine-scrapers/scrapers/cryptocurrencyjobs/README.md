# @job-engine-scrapers/scraper-cryptojobs — Fetch-based scraper for CryptocurrencyJobs.co

Scrapes https://cryptocurrencyjobs.co/engineering/ — a job board for crypto and
blockchain engineering roles. Parses static HTML job listing cards using cheerio.

Data fields: title, company, url, skills (from tags), remote status, category.
Single-page scraper (no pagination).
