#!/usr/bin/env node
/**
 * RemoteOK Scraper — browser-based Playwright scraper for remoteok.com.
 *
 * Fetches job listings from RemoteOK (JS-rendered) using the stealth browser.
 * Extracts jobs from the table-based layout with reliable JSON-LD salary data.
 *
 * Features:
 *   - Batches search terms into compound tags (4 per URL)
 *   - Cloudflare/WAF detection via BrowserScraper base class
 *   - Human-mimic behavior (delays, scrolling) via BrowserScraper base class
 *   - JSON-LD salary extraction
 *   - Tag-based filtering
 *
 * Environment variables:
 *   REMOTEOK_DEBUG — set "1" to save screenshots on failure for debugging.
 */

const { writeOutput, printTopJobs, saveRawData } = require("@job-engine-scrapers/core").output;
const { stableId } = require("@job-engine-scrapers/core").dedup;
const { getTagSet, matchesAnyTag } = require("@job-engine-scrapers/core").tags;
const { extractSkills } = require("@job-engine-scrapers/core").skills;
const { parseJsonLDSalary, parseSalaryRange } = require("@job-engine-scrapers/core").salary;
const BrowserScraper = require("@job-engine-scrapers/core").browserScraper;
const config = require("@job-engine-scrapers/core").config;
const log = require("@job-engine-scrapers/core").logger("remoteok");

const BASE_URL = "https://remoteok.com";
const TAG_SET = getTagSet();

// RemoteOK accepts up to a few keywords combined with + in one URL.
// Batch search terms into small groups to avoid absurdly long URLs.
const BATCH_SIZE = 4;

class RemoteokScraper extends BrowserScraper {
  get id() { return "remoteok"; }
  get platform() { return "remoteok.com"; }

  /**
   * RemoteOK batches search terms into groups of 4 joined by +.
   * Each compound tag produces one URL like /remote-react+node+python+go-jobs.
   * @returns {string[]}
   */
  getSearchTags() {
    const terms = config.getSearchTerms();
    const batches = [];
    for (let i = 0; i < terms.length; i += BATCH_SIZE) {
      batches.push(terms.slice(i, i + BATCH_SIZE).join("+"));
    }
    return batches;
  }

  /**
   * Build a RemoteOK search URL from a compound tag.
   * @param {string} tag — compound tag e.g. "react+node+python+go"
   * @param {number} pageNum — page number (1-based)
   * @returns {string}
   */
  buildUrl(tag, pageNum) {
    return `${BASE_URL}/remote-${encodeURIComponent(tag)}-jobs`;
  }

  /**
   * Extract jobs from the current page.
   * @param {import('playwright').Page} page
   * @param {string} tag — compound search tag
   * @param {number} pageNum — current page number
   * @returns {Promise<Array<object>>}
   */
  async extractJobs(page, tag, pageNum) {
    log.info(`[${this.id}] Extracting page ${pageNum} for "${tag}"`);

    // Wait for job rows
    await page.waitForSelector("table#jobsboard tbody tr.job", { timeout: 20000 }).catch(() => {
      log.warn("Timeout waiting for job rows — falling back");
    });

    // Extract raw job data from DOM
    const rawJobs = await page.evaluate(() => {
      const rows = document.querySelectorAll("table#jobsboard tbody tr.job");
      return Array.from(rows).map((row) => {
        const titleEl = row.querySelector('h2[itemprop="title"]');
        const companyEl = row.querySelector('h3[itemprop="name"]');
        const linkEl = row.querySelector("td.company_and_position a.preventLink");
        const tagsEls = row.querySelectorAll("td.tags h3");
        const locationEls = row.querySelectorAll("div.location.tooltip a");
        const timeEl = row.querySelector("time");
        const jsonldScript = row.querySelector('script[type="application/ld+json"]');

        return {
          title: titleEl?.textContent?.trim() ?? "",
          company: companyEl?.textContent?.trim() ?? "",
          url: linkEl?.getAttribute("href") ?? "",
          tags: Array.from(tagsEls).map((t) => t.textContent?.trim() ?? ""),
          locations: Array.from(locationEls).map((l) => l.textContent?.trim() ?? ""),
          datePosted: timeEl?.getAttribute("datetime") ?? "",
          jsonld: jsonldScript?.textContent ?? "",
          rowText: row.textContent?.slice(0, 2000) ?? "",
        };
      });
    });

    log.info(`[${this.id}] Extracted ${rawJobs.length} raw job rows`);

    // Save page HTML for this batch
    const tagLabel = tag.replace(/[^a-zA-Z0-9]/g, "_");
    const rawPath = saveRawData("remoteok", `page_${pageNum}_${tagLabel}`, await page.content(), "html");
    if (rawPath) {
      log.info(`Saved raw HTML: ${rawPath}`);
    }

    // Filter and build output objects
    const results = [];
    const seenUrls = new Set();

    for (const j of rawJobs) {
      if (!j.title) continue;

      const dedupKey = j.url.split("/").filter(Boolean).pop() || j.title;
      if (seenUrls.has(dedupKey)) continue;
      seenUrls.add(dedupKey);

      const rawText = j.title + " " + j.tags.join(" ") + " " + j.rowText;
      const lowerText = rawText.toLowerCase();
      const tagMatch = matchesAnyTag(TAG_SET, lowerText);
      if (!tagMatch) continue;

      const techStack = extractSkills(rawText);

      const salary = parseJsonLDSalary(j.jsonld);
      let salary_min = salary.salary_min;
      let salary_max = salary.salary_max;
      let currency = salary.currency;

      if (!salary_max && j.rowText) {
        const visible = parseSalaryRange(j.rowText);
        if (visible.salary_max) {
          salary_min = visible.salary_min;
          salary_max = visible.salary_max;
          currency = currency || visible.currency;
        }
      }

      const genericTerms = new Set(["dev", "engineer", "senior", "junior", "full time", "part time", "remote", "apply", "new", "featured", "verified"]);
      const skillTags = techStack.length > 0 ? techStack : j.tags
        .filter((t) => !genericTerms.has(t.toLowerCase()));

      const fullUrl = j.url.startsWith("http") ? j.url : `${BASE_URL}${j.url}`;

      results.push({
        external_id: `remoteok_${j.url.split("/").filter(Boolean).pop() || stableId(j.url)}`,
        platform: "remoteok.com",
        title: j.title,
        company: j.company || "Unknown",
        url: fullUrl,
        salary_min,
        salary_max,
        currency,
        contract_type: "B2B",
        location: j.locations.length > 0 ? j.locations.join(", ") : "Remote",
        remote: true,
        skills: [...new Set(skillTags)],
        category: "",
        experience_level: "",
        requirements: j.jsonld ? `JSON-LD: ${j.jsonld.slice(0, 500)}` : "",
        discovered_at: new Date().toISOString(),
        nice_to_have_skills: "[]",
        languages: "[]",
        published_at: j.datePosted || null,
        expired_at: null,
        last_published_at: null,
        working_time: "full_time",
        latitude: null,
        longitude: null,
        street: "",
        _raw: rawPath ? [rawPath] : [],
      });
    }

    return results;
  }
}

async function main() {
  const scraper = new RemoteokScraper();
  const result = await scraper.scrape();
  writeOutput("remoteok", result.jobs);
  log.info(`→ ${result.count} matching offers`);
  printTopJobs("[RemoteOK]", result.jobs);
  return result;
}

module.exports = {
  metadata: {
    id: "remoteok",
    name: "RemoteOK",
    capabilities: ["browser"],
    needsBrowser: true,
    platform: "remoteok.com",
    configFields: {
      timeout_seconds: {
        type: "number",
        label: "Timeout (seconds)",
        description: "Maximum time per scraper run before timeout (0 = use global default)",
        default: 0,
        min: 0,
        max: 600,
        step: 10,
        unit: "seconds",
      },
    },
  },
  main,
  register(registry) {
    registry.register(this);
  },
};
if (require.main === module) main().catch(err => { console.error("[RemoteOK] Unhandled rejection:", err); process.exit(1); });
