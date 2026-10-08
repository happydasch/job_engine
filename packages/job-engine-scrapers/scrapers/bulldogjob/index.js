#!/usr/bin/env node
/**
 * Bulldogjob Scraper — GraphQL API (public, no auth).
 *
 * Bulldogjob.pl exposes a public GraphQL API that the frontend uses for
 * job search. We call it directly — no WAF issues, no Playwright browser,
 * no cheerio HTML parsing. Response is structured JSON with all fields.
 *
 * Strategy: fetch ALL jobs (no skill filter) in bulk pages of 50, then
 * filter locally with matchesAnyTag() on position + technologyTags.
 * This avoids N separate API calls per tag.
 */

const log = require("@job-engine-scrapers/core").logger("bulldogjob");
const { writeOutput, printTopJobs, saveRawData } = require("@job-engine-scrapers/core").output;
const { sortBySalary, stableId } = require("@job-engine-scrapers/core").dedup;
const { getTagSet, matchesAnyTag } = require("@job-engine-scrapers/core").tags;
const { config } = require("@job-engine-scrapers/core");

const BASE = "https://bulldogjob.pl";
const GRAPHQL_URL = `${BASE}/graphql`;
const PER_PAGE = 50;

const TAG_SET = getTagSet();
const SCRAPER_CFG = config.getScraper("bulldogjob");
const MAX_PAGES = SCRAPER_CFG ? SCRAPER_CFG.max_pages : 10;

// The GraphQL query from the site's frontend — returns all fields needed
// for the job engine schema. No auth required.
const SEARCH_QUERY = `
query searchJobs($page: Int, $perPage: Int) {
  searchJobs(page: $page perPage: $perPage) {
    totalCount
    nodes {
      id
      company { name }
      position
      city
      remote
      experienceLevel
      technologyTags
      contractB2b
      contractEmployment
      contractOther
      employmentType
    }
  }
}
`.trim();

// ——————————————————————————————————————————————————————————————————————————
//  API fetch
// ——————————————————————————————————————————————————————————————————————————

/**
 * Fetch one page of jobs from the GraphQL API.
 * @param {number} page - Page number (1-based)
 * @returns {Promise<{nodes: Array, totalCount: number}|null>}
 */
async function fetchPage(page) {
  const resp = await fetch(GRAPHQL_URL, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Origin: BASE,
    },
    body: JSON.stringify({
      operationName: "searchJobs",
      query: SEARCH_QUERY,
      variables: { page, perPage: PER_PAGE },
    }),
  });

  if (!resp.ok) {
    log.warn(`GraphQL returned HTTP ${resp.status} on page ${page}`);
    return null;
  }

  const body = await resp.json();
  if (body.errors) {
    log.warn(`GraphQL errors on page ${page}: ${body.errors.map((e) => e.message).join(", ")}`);
    return null;
  }

  return body.data?.searchJobs ?? null;
}

/**
 * Normalise experienceLevel string to the job engine schema.
 * @param {string} level
 * @returns {string}
 */
function normaliseExperience(level) {
  switch (level) {
    case "intern": return "intern";
    case "junior": return "junior";
    case "medium": return "mid";
    case "senior": return "senior";
    case "lead": return "lead";
    default: return level || "";
  }
}

/**
 * Derive contract type string from the three boolean fields.
 * @param {object} job
 * @returns {string}
 */
function deriveContractType(job) {
  if (job.contractB2b) return "B2B";
  if (job.contractEmployment) return "UoP";
  if (job.contractOther) return "Other";
  return "";
}

// ——————————————————————————————————————————————————————————————————————————
//  Main
// ——————————————————————————————————————————————————————————————————————————

async function main() {
  log.info(`Starting (GraphQL API, ${PER_PAGE} per page)`);

  const allJobs = new Map();
  let totalCount = 0;

  for (let pageNum = 1; ; pageNum++) {
    const result = await fetchPage(pageNum);
    if (!result || !result.nodes || result.nodes.length === 0) {
      if (pageNum === 1) log.warn("No data returned from API");
      break;
    }

    totalCount = result.totalCount;

    // Save raw API response
    saveRawData("bulldogjob", `page_${pageNum}`, result, "json");

    for (const node of result.nodes) {
      // Combine position + technologyTags for tag matching
      const searchText = [
        node.position || "",
        ...(node.technologyTags || []),
      ]
        .join(" ")
        .toLowerCase();

      if (!matchesAnyTag(TAG_SET, searchText)) continue;

      // Bulldogjob API returns separate nodes for the same job posting with
      // different city values. Dedup by a composite key (position + company)
      // instead of node.id so that location variants merge into one entry.
      const dedupKey = `${(node.position || "").trim()}|${(node.company?.name || "").trim()}`.toLowerCase();
      const url = `${BASE}/companies/jobs/${node.id}`;

      const existing = allJobs.get(dedupKey);
      if (existing) {
        // Merge locations: append city if not already present
        const city = (node.city || "").trim();
        if (city) {
          const existingCities = existing.location.split(", ").map((c) => c.trim());
          if (!existingCities.includes(city)) {
            existingCities.push(city);
            existing.location = existingCities.join(", ");
          }
        }
        // Keep the first URL — all variants point to the same posting page
        continue;
      }

      const externalId = `bulldogjob_${stableId(url)}`;

      allJobs.set(dedupKey, {
        external_id: externalId,
        platform: "bulldogjob.pl",
        title: node.position || "",
        company: node.company?.name || "BulldogJob",
        url,
        salary_min: null,
        salary_max: null,
        currency: "PLN",
        contract_type: deriveContractType(node),
        location: node.city || "",
        remote: !!node.remote,
        skills: node.technologyTags || [],
        category: "",
        experience_level: normaliseExperience(node.experienceLevel),
        requirements: "",
        discovered_at: new Date().toISOString(),
      });
    }

    // Stop if we've fetched all available pages or hit the max pages limit
    const totalPages = Math.ceil(totalCount / PER_PAGE);
    const stopReason = pageNum >= totalPages
      ? `Reached last page (${pageNum}/${totalPages})`
      : pageNum >= MAX_PAGES
        ? `Reached max pages limit (${MAX_PAGES})`
        : null;
    if (stopReason) {
      log.info(stopReason);
      break;
    }
  }

  const jobs = sortBySalary([...allJobs.values()]);
  writeOutput("bulldogjob", jobs);
  log.info(`Wrote ${jobs.length} jobs (total in API: ${totalCount})`);

  printTopJobs("[Bulldogjob]", jobs);

  return { platform: "bulldogjob.pl", count: jobs.length, jobs };
}

module.exports = {
  metadata: {
    id: "bulldogjob",
    name: "BulldogJob",
    capabilities: ["fetch"],
    needsBrowser: false,
    platform: "bulldogjob.pl",
    configFields: {
      max_pages: {
        type: "number",
        label: "Max Pages",
        description: "Maximum number of pagination pages to scrape (50 items/page)",
        default: 10,
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
if (require.main === module) main().catch((err) => { console.error("[Bulldogjob] Fatal:", err); process.exit(1); });
