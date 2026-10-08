#!/usr/bin/env node
/**
 * {{displayName}} Scraper — API-based.
 *
 * Fetches job listings from {{displayName}}'s public API.
 * TODO: Describe the API structure, any auth requirements, rate limits, etc.
 */

const log = require("@job-engine-scrapers/core").logger("{{id}}");
const { fetchJson } = require("@job-engine-scrapers/core").fetch;
const { writeOutput, printTopJobs, saveRawData } = require("@job-engine-scrapers/core").output;
const { deduplicateByKey, sortBySalary, stableId } = require("@job-engine-scrapers/core").dedup;
const { getTagSet, matchesAnyTag } = require("@job-engine-scrapers/core").tags;
const { extractSkills } = require("@job-engine-scrapers/core").skills;
const config = require("@job-engine-scrapers/core").config;

// TODO: Set your API base URL
const BASE_URL = "https://api.{{id}}.com";

const TAGS = config.getTags();
const TAG_SET = getTagSet();
const SCRAPER_CFG = config.getScraper("{{id}}");
const MAX_PAGES = SCRAPER_CFG ? SCRAPER_CFG.max_pages : 5;

// ─── API Fetch ─────────────────────────────────────────────────────────────

/**
 * Fetch one page of jobs from the API.
 * TODO: Adapt to the actual API structure (endpoint, pagination, auth).
 */
async function fetchPage(pageNum) {
  // TODO: Add API key / auth headers if the API requires authentication.
  //       Example: const headers = { Authorization: "Bearer YOUR_TOKEN" };
  const url = `${BASE_URL}/jobs?page=${pageNum}`;

  const body = await fetchJson(url, {}, "{{displayName}}");
  if (!body) {
    log.warn(`No data from API — page ${pageNum} done`);
    return { items: [], done: true };
  }

  // Save raw API response for debugging
  const rawPath = saveRawData("{{id}}", `page_${pageNum}`, body, "json");

  // TODO: Extract the items array from the response structure
  // Common patterns: body.data, body.results, body.jobs, body.offers
  const items = body.data ?? body.results ?? body.jobs ?? body.offers ?? [];
  for (const item of items) {
    if (rawPath) item._raw = [rawPath];
  }

  // TODO: Determine when pagination is complete
  const done = items.length === 0 || pageNum >= MAX_PAGES;
  return { items, done };
}

// ─── Tag Matching ──────────────────────────────────────────────────────────

/**
 * Check if a job matches any of the user's tags.
 * Searches title, description, and skills arrays (OR logic).
 * TODO: Adjust which fields are searched if the API has different field names.
 */
function isMatch(item) {
  const title = (item.title ?? "").toLowerCase();
  const description = (item.description ?? item.body ?? "").toLowerCase();
  const skills = (item.skills ?? item.tech_stack ?? item.technologies ?? []).map(
    (s) => (typeof s === "string" ? s : (s.name ?? "")).toLowerCase()
  );
  const allText = title + " " + description + " " + skills.join(" ");
  return matchesAnyTag(TAG_SET, allText);
}

// ─── Parse Item ────────────────────────────────────────────────────────────

/**
 * Map an API response item to a JobOffer object.
 * TODO: Map ALL relevant fields from the API response to match JobOffer contract.
 */
function parseItem(item) {
  return {
    external_id: `{{id}}_${stableId(item.id ?? item.url ?? item.guid ?? JSON.stringify(item))}`,
    platform: "{{displayName}}",
    title: item.title ?? "Unknown",
    company: item.company ?? item.company_name ?? item.employer ?? "Unknown",
    url: item.url ?? item.link ?? item.apply_url ?? "",

    salary_min: item.salary_min ?? item.salaryFrom ?? item.salary?.min ?? null,
    salary_max: item.salary_max ?? item.salaryTo ?? item.salary?.max ?? null,
    currency: item.currency ?? "USD",
    contract_type: item.contract_type ?? item.type ?? "full_time",
    location: item.location ?? item.city ?? item.region ?? "Remote",
    remote: /remote/i.test(item.location ?? item.workplace ?? ""),
    skills: (item.skills ?? item.tech_stack ?? item.technologies ?? []).map(
      (s) => (typeof s === "string" ? s.toLowerCase() : (s.name ?? "").toLowerCase())
    ),
    category: item.category ?? "",
    experience_level: item.experience_level ?? item.seniority ?? item.level ?? "",
    requirements: item.description ?? item.body ?? "",
    discovered_at: new Date().toISOString(),

    // Enrichment fields (set if the API provides them)
    nice_to_have_skills: item.nice_to_have_skills
      ? JSON.stringify(
          (Array.isArray(item.nice_to_have_skills) ? item.nice_to_have_skills : [])
            .map((s) => (typeof s === "string" ? s.toLowerCase() : (s.name ?? "").toLowerCase()))
        )
      : "[]",
    languages: item.languages ? JSON.stringify(item.languages) : "[]",
    published_at: item.published_at ?? item.date ?? item.posted_at ?? null,
    expired_at: item.expired_at ?? null,
    working_time: item.working_time ?? item.employment_type ?? "full_time",
    latitude: item.latitude ?? null,
    longitude: item.longitude ?? null,
    street: item.street ?? "",

    _raw: item._raw ?? [],
  };
}

// ─── Main ──────────────────────────────────────────────────────────────────

async function main() {
  try {
    const allJobs = new Map();

    for (let page = 1; page <= MAX_PAGES; page++) {
      log.info(`Fetching page ${page}…`);

      const { items, done } = await fetchPage(page);
      if (items.length === 0) break;

      for (const item of items) {
        if (!isMatch(item)) continue;
        const job = parseItem(item);
        if (!allJobs.has(job.external_id)) {
          allJobs.set(job.external_id, job);
        }
      }

      if (done) break;
    }

    const jobs = sortBySalary(deduplicateByKey([...allJobs.values()], (j) => j.external_id));
    writeOutput("{{id}}", jobs);
    log.info(`${jobs.length} matching offers`);

    return { platform: "{{displayName}}", count: jobs.length, jobs };
  } catch (err) {
    log.error("Fatal:", err.message);
    return { platform: "{{displayName}}", count: 0, jobs: [] };
  }
}

if (require.main === module) {
  main().catch((err) => {
    console.error("[{{id}}] Fatal:", err);
    process.exit(1);
  });
}

module.exports = {
  metadata: {
    id: "{{id}}",
    name: "{{displayName}}",
    capabilities: ["api"],
    needsBrowser: false,
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
