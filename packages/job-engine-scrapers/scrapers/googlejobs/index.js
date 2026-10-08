#!/usr/bin/env node
/**
 * Google Jobs Scraper — extends BrowserScraper.
 *
 * Uses search terms (boosted_keywords) instead of 90 individual tags,
 * pagination support, and only saves HTML when jobs are actually found.
 *
 * Environment:
 *   GOOGLE_JOBS_COOKIE — optional cookie string for authenticated search
 *
 * Config (data/scraper_config.yaml):
 *   googlejobs:
 *     enabled: true
 *     max_pages: 1
 *     request_delay_ms: 2000
 *     batch_size: 5          # tags per URL when no boosted_keywords
 */

const log = require("@job-engine-scrapers/core").logger("googlejobs");
const { extractSkills } = require("@job-engine-scrapers/core").skills;
const { writeOutput, printTopJobs, saveRawData } = require("@job-engine-scrapers/core").output;
const { stableId } = require("@job-engine-scrapers/core").dedup;
const { getTagSet, matchesAnyTag } = require("@job-engine-scrapers/core").tags;
const config = require("@job-engine-scrapers/core").config;
const { parseSalaryRange, parseHourlyRateToYearly, detectCurrency } = require("@job-engine-scrapers/core").salary;
const BrowserScraper = require("@job-engine-scrapers/core").browserScraper;

const TAG_SET = getTagSet();

// ─── GooglejobsScraper class — extends BrowserScraper ─────────────────────

class GooglejobsScraper extends BrowserScraper {
  get id() { return "googlejobs"; }
  get platform() { return "google.com/jobs"; }

  /** Return search queries: search terms + "job" or batched tags with OR */
  getSearchTags() {
    const searchTerms = config.getSearchTerms();
    const tags = config.getTags();
    const cfg = this.getScraperConfig();
    const batchSize = cfg.batch_size || 5;

    if (searchTerms.length > 0) {
      return searchTerms.map(t => t + " job");
    }
    // Batch tags using Google's OR operator — fewer page loads
    const queries = [];
    for (let i = 0; i < tags.length; i += batchSize) {
      const batch = tags.slice(i, i + batchSize);
      queries.push("(" + batch.join(" OR ") + ") job");
    }
    return queries;
  }

  /** Build Google search URL with pagination via &start=N */
  buildUrl(tag, pageNum) {
    const base = "https://www.google.com/search?q=" + encodeURIComponent(tag) + "&ibp=htl;jobs";
    if (pageNum > 1) {
      return base + "&start=" + ((pageNum - 1) * 10);
    }
    return base;
  }

  /** Override navigateToPage with 20s timeout for google.com */
  async navigateToPage(page, url) {
    try {
      await page.goto(url, { waitUntil: "domcontentloaded", timeout: 20000 });
    } catch (err) {
      log.info(`[${this.id}] Navigation failed for ${url} (${err.message})`);
      return false;
    }
    const blocked = await this.detectWaf(page);
    if (blocked) {
      log.info(`[${this.id}] Blocked at ${url}`);
      if (this.debug) {
        await page.screenshot({ path: `/tmp/${this.id}_blocked.png`, fullPage: false }).catch(() => {});
      }
      return false;
    }
    return true;
  }

  /** Detect WAF: base class patterns + google-specific patterns */
  async detectWaf(page) {
    const baseBlocked = await super.detectWaf(page);
    if (baseBlocked) return true;

    return page.evaluate(() => {
      const title = document.title.toLowerCase();
      const body = (document.body && document.body.innerText || "").toLowerCase();
      return (
        // EU cookie-consent interstitial redirects every search to consent.google.com
        location.hostname.indexOf("consent.") === 0 ||
        location.pathname.indexOf("/sorry/") === 0 ||
        title.indexOf("sorry") !== -1 ||
        body.indexOf("unusual traffic") !== -1 ||
        body.indexOf("automated queries") !== -1
      );
    }).catch(() => false);
  }

  /** Inject GOOGLE_JOBS_COOKIE if set */
  async onLaunch() {
    const cookieStr = process.env.GOOGLE_JOBS_COOKIE;
    if (!cookieStr || !this.page) return;

    try {
      const cookies = JSON.parse(cookieStr);
      if (Array.isArray(cookies)) {
        await this.page.context().addCookies(cookies.map(c => ({
          name: c.name,
          value: c.value,
          domain: c.domain || ".google.com",
          path: c.path || "/",
        })));
        log.info("Applied session cookies from GOOGLE_JOBS_COOKIE");
      }
    } catch (e) {
      log.info("Could not parse GOOGLE_JOBS_COOKIE — skipping cookie injection");
    }
  }

  /** Extract job cards from DOM, filter by tags, parse salary, build output */
  async extractJobs(page, tag, pageNum) {
    log.info(`[${this.id}] Searching "${tag}" page ${pageNum}…`);

    // Wait for job cards
    try {
      await page.waitForSelector(
        '[class*="job-card"], [class*="jobs-card"], [jsname*="job"], li[class*="job"]',
        { timeout: 8000 }
      );
    } catch (e) {
      // No job cards found — check for job-related content
      const hasResults = await page.evaluate(() => {
        const text = document.body && document.body.innerText || "";
        return text.indexOf("No results") === -1 && text.indexOf("did not match") === -1;
      });
      if (!hasResults) {
        log.info("No results for \"" + tag + "\"");
        return [];
      }
      const jobText = await page.evaluate(() => {
        return (document.body && document.body.innerText || "").toLowerCase();
      });
      if (jobText.indexOf("job") === -1 && jobText.indexOf("hiring") === -1 && jobText.indexOf("salary") === -1) {
        log.info("No job content found for \"" + tag + "\"");
        return [];
      }
    }

    // Extract all cards from DOM
    const rawJobs = await page.evaluate(() => {
      const cards = document.querySelectorAll(
        '[class*="job-card"], [class*="jobs-card"], [jsname*="job"], li[class*="job"], div[class*="card"], article'
      );
      return Array.from(cards).map((card) => {
        const titleEl = card.querySelector("h2, h3, [class*='title']");
        const companyEl = card.querySelector("[class*='company'], [class*='employer']");
        const locationEl = card.querySelector("[class*='location']");
        const salaryEl = card.querySelector("[class*='salary']");
        const linkEl = card.querySelector("a[href]");
        return {
          title: titleEl && titleEl.textContent ? titleEl.textContent.trim() : "",
          company: companyEl && companyEl.textContent ? companyEl.textContent.trim() : "",
          location: locationEl && locationEl.textContent ? locationEl.textContent.trim() : "",
          salary: salaryEl && salaryEl.textContent ? salaryEl.textContent.trim() : "",
          url: linkEl && linkEl.href ? linkEl.href : "",
          text: card.textContent ? card.textContent.slice(0, 1200) : "",
        };
      });
    });

    const validJobs = rawJobs.filter(j => j.title);
    if (validJobs.length === 0) return [];

    // Save raw HTML only when jobs found
    const label = tag.replace(/[^a-zA-Z0-9]/g, "_").slice(0, 100);
    const rawPath = saveRawData("googlejobs", label, await page.content(), "html");
    if (rawPath) {
      log.info("Saved raw HTML: " + rawPath);
    }

    // Filter, parse, and build output objects
    const results = [];
    for (const job of validJobs) {
      const rawText = job.title + " " + job.text;
      const text = rawText.toLowerCase();
      if (!matchesAnyTag(TAG_SET, text)) continue;

      // Salary parsing using shared functions
      let salaryMin = null;
      let salaryMax = null;
      let currency = "USD";

      if (/\/hr|per hour|hourly/i.test(job.salary)) {
        const hourly = parseHourlyRateToYearly(job.salary);
        if (hourly.salary_min !== null) salaryMin = hourly.salary_min;
        if (hourly.salary_max !== null) salaryMax = hourly.salary_max;
        currency = detectCurrency(job.salary) || "USD";
      } else {
        const sal = parseSalaryRange(job.salary);
        salaryMin = sal.salary_min;
        salaryMax = sal.salary_max;
        currency = sal.currency || "USD";
      }

      const techStack = extractSkills(rawText);
      const isRemote = /remote/i.test(job.location || job.text);

      results.push({
        external_id: "googlejobs_" + stableId(job.url || job.title + job.company),
        platform: "google.com/jobs",
        title: job.title,
        company: job.company || "Unknown",
        url: job.url || "https://www.google.com/search?q=" + encodeURIComponent(tag) + "&ibp=htl;jobs",
        salary_min: salaryMin,
        salary_max: salaryMax,
        currency: currency || "USD",
        contract_type: "B2B",
        location: job.location || "Remote",
        remote: isRemote,
        skills: [...new Set(techStack)],
        category: "",
        experience_level: "",
        description: job.text.slice(0, 2000),
        discovered_at: new Date().toISOString(),
        nice_to_have_skills: "[]",
        languages: "[]",
        published_at: null,
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

// ─── Main ───────────────────────────────────────────────────────────────

async function main() {
  const searchTerms = config.getSearchTerms();
  const tags = config.getTags();
  const queries = (searchTerms.length > 0)
    ? searchTerms.map(t => t + " job")
    : ((tags.length > 0) ? ["(" + tags.slice(0, 5).join(" OR ") + ") job"] : []);

  if (queries.length === 0) {
    log.info("No search terms or tags configured — nothing to search");
    return { platform: "google.com/jobs", count: 0, jobs: [] };
  }

  log.info("Using " + queries.length + " search queries");

  const scraper = new GooglejobsScraper();
  const result = await scraper.scrape();

  if (result.jobs.length > 0) {
    writeOutput("googlejobs", result.jobs);
  }
  log.info("→ " + result.count + " matching offers");
  printTopJobs("[googlejobs]", result.jobs);

  return result;
}

if (require.main === module) {
  main().catch(err => {
    console.error("[googlejobs] Fatal:", err);
    process.exit(1);
  });
}

module.exports = {
  metadata: {
    id: "googlejobs",
    name: "Google Jobs",
    capabilities: ["browser"],
    needsBrowser: true,
    platform: "google.com/jobs",
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
      max_pages: {
        type: "number",
        label: "Max Pages",
        description: "Pagination pages per search term",
        default: 1,
        min: 1,
        max: 10,
        step: 1,
      },
      request_delay_ms: {
        type: "number",
        label: "Request Delay (ms)",
        description: "Politeness delay between page navigations (milliseconds)",
        default: 2000,
        min: 0,
        max: 10000,
        step: 500,
        unit: "ms",
      },
      batch_size: {
        type: "number",
        label: "Batch Size",
        description: "Number of tags to combine per search URL (used when no boosted keywords)",
        default: 5,
        min: 1,
        max: 20,
        step: 1,
      },
    },
  },
  main,
  register(registry) {
    registry.register(this);
  },
};
