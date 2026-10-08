#!/usr/bin/env node
/**
 * Jooble Scraper — official Jooble API (https://jooble.org/api/about).
 *
 * WHY THE API (and not HTML): jooble.org sits behind Cloudflare. Plain fetch
 * gets a 403 "Just a moment…" challenge, and even a stealth headless browser
 * only renders the SPA chrome — the vacancy list never populates (bot-detected
 * at the data layer). The previous HTML-card scraper therefore returned 0
 * results: its search URL (`/Search/<tag>/IT-jobs`) 404s now, and its obfuscated
 * card selectors (`_jobCard`, `_8w9Ce2`, `Vk-5Da`) no longer exist.
 *
 * The official API is the supported, ToS-compliant integration: a POST to
 * `https://jooble.org/api/{key}` with `{ keywords, location, page }` returns
 * structured JSON. It needs a FREE API key (request one at
 * https://jooble.org/api/about) supplied via scraper_config.yaml
 * scrapers.jooble.api_key.
 *
 * Without a key the scraper throws an actionable error so the run reports it.
 *
 * Config options (scraper_config.yaml → scrapers.jooble):
 *   api_key    — Jooble API key
 *   location   — location filter passed to the API, e.g. "Poland", "Remote" ("" = any)
 *   max_pages  — API result pages to fetch per search tag (default 1)
 */

const log = require("@job-engine-scrapers/core").logger("jooble");
const { fetchJson } = require("@job-engine-scrapers/core").fetch;
const { writeOutput, printTopJobs, saveRawData } = require("@job-engine-scrapers/core").output;
const { sortBySalary, stableId } = require("@job-engine-scrapers/core").dedup;
const { getTagSet, matchesAnyTag } = require("@job-engine-scrapers/core").tags;
const { parseSalaryRange, detectCurrency } = require("@job-engine-scrapers/core").salary;
const config = require("@job-engine-scrapers/core").config;

const TAGS = config.getTags();
const TAG_SET = getTagSet();
const SCRAPER_CFG = config.getScraper("jooble") || {};
const MAX_PAGES = SCRAPER_CFG.max_pages > 0 ? SCRAPER_CFG.max_pages : 1;
const LOCATION = typeof SCRAPER_CFG.location === "string" ? SCRAPER_CFG.location : "";
const API_KEY = SCRAPER_CFG.api_key;
const MAX_OFFER_DURATION_DAYS = config.getMaxOfferDurationDays ? config.getMaxOfferDurationDays() : 30;

const API_BASE = "https://jooble.org/api";

// ——————————————————————————————————————————————————————————————————————————
//  API
// ——————————————————————————————————————————————————————————————————————————

/**
 * Fetch one page of results for a keyword from the Jooble API.
 * @param {string} keywords
 * @param {number} page — 1-based
 * @returns {Promise<{jobs: Array, totalCount: number}|null>}
 */
async function fetchPage(keywords, page) {
  const body = { keywords, location: LOCATION, page: String(page) };
  const data = await fetchJson(
    `${API_BASE}/${API_KEY}`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
        Origin: "https://jooble.org",
        Referer: "https://jooble.org/",
      },
      body: JSON.stringify(body),
      maxRetries: 2,
    },
    "[Jooble]"
  );
  if (!data || !Array.isArray(data.jobs)) return null;
  return { jobs: data.jobs, totalCount: data.totalCount || data.jobs.length };
}

/**
 * Parse a Jooble salary string ("$50,000 - $70,000 per year", "8 000 zł" …).
 * @param {string} text
 * @returns {{ salary_min: number|null, salary_max: number|null, currency: string }}
 */
function parseSalary(text) {
  if (!text || typeof text !== "string") return { salary_min: null, salary_max: null, currency: "" };
  const range = parseSalaryRange(text);
  return {
    salary_min: range.salary_min,
    salary_max: range.salary_max,
    currency: range.currency || detectCurrency(text) || "",
  };
}

/**
 * Convert the Jooble `updated` ISO timestamp to a published_at date, filtering
 * out postings older than the configured max offer duration.
 * @param {string} updated — ISO 8601
 * @returns {string|null}
 */
function parsePublishedAt(updated) {
  if (!updated) return null;
  const ts = Date.parse(updated);
  if (Number.isNaN(ts)) return null;
  const ageDays = (Date.now() - ts) / 86_400_000;
  if (ageDays > MAX_OFFER_DURATION_DAYS) return null;
  return new Date(ts).toISOString();
}

// ——————————————————————————————————————————————————————————————————————————
//  Main
// ——————————————————————————————————————————————————————————————————————————

async function main() {
  if (!API_KEY) {
    throw new Error(
      "[jooble] No API key configured — set scrapers.jooble.api_key in scraper_config.yaml " +
        "(free key at https://jooble.org/api/about) or disable the scraper."
    );
  }

  log.info(`Starting (official API, ${TAGS.length} search tags, ${MAX_PAGES} page(s)/tag, location: "${LOCATION || "any"}")`);

  const allJobs = new Map();

  for (const tag of TAGS) {
    for (let page = 1; page <= MAX_PAGES; page++) {
      const result = await fetchPage(tag, page);
      if (!result) {
        if (page === 1) log.warn(`"${tag}": no data from API`);
        break;
      }

      saveRawData("jooble", `search_${tag.replace(/[^a-zA-Z0-9]/g, "_")}_page_${page}`, result, "json");
      log.info(`"${tag}" page ${page}: ${result.jobs.length} jobs (total ${result.totalCount})`);

      for (const job of result.jobs) {
        const title = (job.title || "").trim();
        const link = job.link || "";
        if (!title || !link) continue;

        const searchText = `${title} ${job.snippet || ""} ${job.company || ""}`.toLowerCase();
        if (!matchesAnyTag(TAG_SET, searchText)) continue;

        const publishedAt = parsePublishedAt(job.updated);
        // Drop stale postings when we have a reliable timestamp.
        if (job.updated && publishedAt === null) continue;

        const externalId = `jooble_${stableId(link)}`;
        if (allJobs.has(externalId)) continue;

        const sal = parseSalary(job.salary);
        const location = (job.location || "").trim();
        const isRemote = /remote|zdaln/i.test(`${location} ${title} ${job.type || ""}`);

        allJobs.set(externalId, {
          external_id: externalId,
          platform: "jooble.org",
          title,
          company: (job.company || "").trim() || "Unknown",
          url: link,
          salary_min: sal.salary_min,
          salary_max: sal.salary_max,
          currency: sal.currency || "",
          contract_type: job.type || "",
          location,
          remote: isRemote,
          skills: [],
          category: "",
          experience_level: "",
          requirements: (job.snippet || "").replace(/<[^>]*>/g, " ").replace(/\s+/g, " ").trim().slice(0, 2000),
          discovered_at: new Date().toISOString(),
          published_at: publishedAt,
        });
      }

      if (page >= Math.ceil(result.totalCount / 20)) break; // API returns ~20/page
    }
  }

  const jobs = sortBySalary([...allJobs.values()]);
  writeOutput("jooble", jobs);
  log.info(`Wrote ${jobs.length} jobs`);
  printTopJobs("[Jooble]", jobs);

  return { platform: "jooble.org", count: jobs.length, jobs };
}

module.exports = {
  metadata: {
    id: "jooble",
    name: "Jooble",
    capabilities: ["fetch"],
    needsBrowser: false,
    platform: "jooble.org",
    configFields: {
      api_key: {
        type: "password",
        label: "API Key",
        description: "Jooble API key (free at https://jooble.org/api/about).",
        default: "",
        secret: true,
      },
      location: {
        type: "string",
        label: "Location",
        description: 'Location filter passed to the API, e.g. "Poland", "Remote". Empty = any location.',
        default: "",
      },
      max_pages: {
        type: "number",
        label: "Max Pages",
        description: "API result pages to fetch per search tag (~20 results/page)",
        default: 1,
        min: 1,
        max: 20,
        unit: "pages",
      },
    },
  },
  main,
  register(registry) {
    registry.register(this);
  },
};

if (require.main === module) main().catch((err) => { console.error("[Jooble] Fatal:", err); process.exit(1); });
