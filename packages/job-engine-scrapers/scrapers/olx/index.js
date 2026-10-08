#!/usr/bin/env node
/**
 * OLX Scraper — direct JSON API with search queries.
 *
 * OLX is a general classifieds site in Poland. Category 4 (jobs) returns
 * mostly non-tech listings (delivery, retail, construction, etc.), so we
 * search by high-signal terms (boosted_keywords from profile) to surface
 * relevant tech roles. Results are merged, deduplicated, and filtered by
 * tags and date.
 *
 * API: https://www.olx.pl/api/v1/offers?category_id=4&query=...
 * Pagination: ?offset=N (from links.next.href)
 */

const log = require("@job-engine-scrapers/core").logger("olx");
const { fetchJson } = require("@job-engine-scrapers/core").fetch;
const { writeOutput, printTopJobs, saveRawData } = require("@job-engine-scrapers/core").output;
const { sortBySalary, stableId } = require("@job-engine-scrapers/core").dedup;
const { getTagSet, matchesAnyTag } = require("@job-engine-scrapers/core").tags;
const config = require("@job-engine-scrapers/core").config;

const TAG_SET = getTagSet();
const SCRAPER_CFG = config.getScraper("olx");
const MAX_PAGES = SCRAPER_CFG ? SCRAPER_CFG.max_pages ?? 1 : 1;
const MAX_OFFER_DURATION_DAYS = config.getMaxOfferDurationDays ? config.getMaxOfferDurationDays() : 30;

// Use search terms (boosted_keywords) — OLX is a general board; searching
// all 79 granular tags is wasteful. The profile's boosted_keywords are the
// high-signal terms (e.g. python, fastapi, llm, trading).
const SEARCH_TERMS = config.getSearchTerms();

// ——————————————————————————————————————————————————————————————————————————
//  Date filtering
// ——————————————————————————————————————————————————————————————————————————

function isFresh(createdTime, maxDays) {
  if (!createdTime) return true;
  const created = new Date(createdTime);
  if (isNaN(created.getTime())) return true;
  const now = new Date();
  const diffDays = (now - created) / (1000 * 60 * 60 * 24);
  return diffDays <= maxDays;
}

// ——————————————————————————————————————————————————————————————————————————
//  Fetch a single page for a search term
// ——————————————————————————————————————————————————————————————————————————

async function fetchSearchPage(searchTerm, offset, pageNum) {
  const url = `https://www.olx.pl/api/v1/offers?category_id=4&limit=40&query=${encodeURIComponent(searchTerm)}${offset > 0 ? `&offset=${offset}` : ""}`;
  const data = await fetchJson(url, {}, "[OLX]");
  if (!data || !data.data) return { items: [], nextUrl: null };

  const rawPath = saveRawData("olx", `${searchTerm.replace(/[^a-z0-9]+/g, "_")}_page_${pageNum}`, data, "json");
  if (rawPath) {
    log.info(`Saved raw data: ${rawPath}`);
  }

  const nextUrl = data.links?.next?.href ?? null;
  const items = data.data.map((item) => {
    if (rawPath) item._raw = [rawPath];
    return item;
  });
  return { items, nextUrl };
}

// ——————————————————————————————————————————————————————————————————————————
//  Normalize an OLX offer into a job record
// ——————————————————————————————————————————————————————————————————————————

function toJobRecord(item) {
  const title = item.title ?? "";
  const url = item.url ?? "";
  if (!title || !url) return null;

  // Date filtering
  if (!isFresh(item.created_time, MAX_OFFER_DURATION_DAYS)) return null;

  // Tag filtering — secondary filter on top of search query
  if (!matchesAnyTag(TAG_SET, title.toLowerCase())) return null;

  // Normalize offer URL
  const fullUrl = url.startsWith("http") ? url : `https://www.olx.pl${url.startsWith("/") ? "" : "/"}${url}`;

  return {
    external_id: `olx_${stableId(fullUrl)}`,
    platform: "olx.pl",
    title,
    company: "OLX",
    url: fullUrl,
    salary_min: null,
    salary_max: null,
    currency: "PLN",
    contract_type: "",
    location: "",
    remote: false,
    skills: [],
    category: "",
    experience_level: "",
    requirements: "",
    discovered_at: new Date().toISOString(),
    _raw: item._raw ?? [],
  };
}

// ——————————————————————————————————————————————————————————————————————————
//  Main
// ——————————————————————————————————————————————————————————————————————————

async function main() {
  log.info(`Starting (${SEARCH_TERMS.length} search terms, max ${MAX_PAGES} pages each)`);

  const allJobs = new Map();

  for (const term of SEARCH_TERMS) {
    log.info(`Searching term: "${term}"`);
    let offset = 0;
    let pageNum = 0;
    let termJobs = 0;

    while (pageNum < MAX_PAGES) {
      pageNum++;
      const { items, nextUrl } = await fetchSearchPage(term, offset, pageNum);

      for (const item of items) {
        const record = toJobRecord(item);
        if (record && !allJobs.has(record.external_id)) {
          allJobs.set(record.external_id, record);
          termJobs++;
        }
      }

      log.info(`  page ${pageNum}: ${items.length} items, ${termJobs} new matches for "${term}"`);

      if (!nextUrl) break;
      // Extract offset from nextUrl
      const nextOffsetMatch = nextUrl.match(/[?&]offset=(\d+)/);
      if (nextOffsetMatch) {
        offset = parseInt(nextOffsetMatch[1], 10);
      } else {
        break;
      }
    }
  }

  const jobs = sortBySalary([...allJobs.values()]);
  writeOutput("olx", jobs);
  log.info(`Wrote ${jobs.length} jobs total`);

  printTopJobs("[OLX]", jobs);

  return { platform: "olx.pl", count: jobs.length, jobs };
}

module.exports = {
  metadata: {
    id: "olx",
    name: "OLX",
    capabilities: ["fetch"],
    needsBrowser: false,
    platform: "olx.pl",
    configFields: {
      max_pages: {
        type: "number",
        label: "Max Pages",
        description: "Maximum number of pagination pages to scrape",
        default: 5,
        min: 1,
        max: 100,
        unit: "pages",
      },
    },
  },
  main,
  register(registry) {
    registry.register(this);
  },
};
if (require.main === module) main().catch((err) => { console.error("[OLX] Fatal:", err); process.exit(1); });