#!/usr/bin/env node
/**
 * {{displayName}} Scraper — HTML fetch-based.
 *
 * Fetches and parses HTML from {{displayName}}'s job listing pages.
 * TODO: Describe the site's HTML structure, selectors, pagination, etc.
 */

const log = require("@job-engine-scrapers/core").logger("{{id}}");
const { fetchHtml } = require("@job-engine-scrapers/core").fetch;
const { writeOutput, printTopJobs, saveRawData } = require("@job-engine-scrapers/core").output;
const { deduplicateByKey, sortBySalary, stableId } = require("@job-engine-scrapers/core").dedup;
const { getTagSet, matchesAnyTag } = require("@job-engine-scrapers/core").tags;
const { extractSkills } = require("@job-engine-scrapers/core").skills;
const config = require("@job-engine-scrapers/core").config;

// TODO: Set your search URL template
const SEARCH_URL = "https://{{id}}.com/search?q=";

const TAGS = config.getTags();
const TAG_SET = getTagSet();
const SCRAPER_CFG = config.getScraper("{{id}}");
const MAX_PAGES = SCRAPER_CFG ? SCRAPER_CFG.max_pages : 5;

// ─── HTML Parsing ──────────────────────────────────────────────────────────

/**
 * Parse job listings from HTML.
 * TODO: Implement HTML parsing. Cheerio is recommended:
 *       const cheerio = require("cheerio");
 *       const $ = cheerio.load(html);
 *       Then use CSS selectors to extract job data.
 *
 * Fields to extract per job: title, company, url, location, salary, description.
 */
function parseJobsFromHtml(html, tag) {
  const jobs = [];
  // TODO: Parse the HTML into job objects.
  // Example (with cheerio):
  //   const $ = cheerio.load(html);
  //   $(".job-card, .job-listing, .posting").each((i, el) => {
  //     const $el = $(el);
  //     jobs.push({
  //       title: $el.find(".title, h2, h3").text().trim(),
  //       company: $el.find(".company, .employer").text().trim(),
  //       url: $el.find("a[href]").attr("href") ?? "",
  //       location: $el.find(".location, .city").text().trim(),
  //       salary: $el.find(".salary, .compensation").text().trim(),
  //       text: $el.text().slice(0, 1200),
  //     });
  //   });
  return jobs;
}

// ─── Main ──────────────────────────────────────────────────────────────────

async function main() {
  try {
    const allJobs = new Map();

    for (const tag of TAGS) {
      log.info(`Searching "${tag}"…`);

      for (let page = 1; page <= MAX_PAGES; page++) {
        // TODO: Adapt URL for pagination if applicable
        const url = `${SEARCH_URL}${encodeURIComponent(tag)}&page=${page}`;

        const html = await fetchHtml(url, "{{displayName}}");
        if (!html) continue;

        // Save raw HTML for debugging
        const rawPath = saveRawData("{{id}}", `${tag}_page_${page}`, html, "html");

        const rawJobs = parseJobsFromHtml(html, tag);
        if (rawJobs.length === 0) break;

        for (const job of rawJobs) {
          const text = (job.title + " " + (job.text ?? "")).toLowerCase();
          if (!matchesAnyTag(TAG_SET, text)) continue;

          const techStack = extractSkills(text);
          const isRemote = /remote/i.test(job.location ?? "");

          const output = {
            external_id: `{{id}}_${stableId(job.url || job.title + (job.company ?? ""))}`,
            platform: "{{displayName}}",
            title: job.title,
            company: job.company || "Unknown",
            url: job.url || url,
            salary_min: job.salary_min ?? null,
            salary_max: job.salary_max ?? null,
            currency: job.currency ?? "USD",
            contract_type: "full_time",
            location: job.location || "Remote",
            remote: isRemote,
            skills: [...new Set(techStack)],
            category: "",
            experience_level: "",
            requirements: (job.description ?? job.text ?? "").slice(0, 2000),
            discovered_at: new Date().toISOString(),
            nice_to_have_skills: "[]",
            languages: "[]",
            published_at: null,
            expired_at: null,
            working_time: "full_time",
            latitude: null,
            longitude: null,
            street: "",
            _raw: rawPath ? [rawPath] : [],
          };

          if (!allJobs.has(output.external_id)) {
            allJobs.set(output.external_id, output);
          }
        }
      }
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
    capabilities: ["fetch"],
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