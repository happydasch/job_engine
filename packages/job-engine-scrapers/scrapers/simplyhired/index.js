#!/usr/bin/env node
/**
 * SimplyHired Scraper — extends BrowserScraper.
 *
 * Searches SimplyHired for each search tag, extracts job listings from the
 * JavaScript-rendered DOM, and filters for matching tags.
 */

const log = require("@job-engine-scrapers/core").logger("simplyhired");
const { extractSkills } = require("@job-engine-scrapers/core").skills;
const { writeOutput, printTopJobs, saveRawData } = require("@job-engine-scrapers/core").output;
const { stableId } = require("@job-engine-scrapers/core").dedup;
const { getTagSet, matchesAnyTag } = require("@job-engine-scrapers/core").tags;
const BrowserScraper = require("@job-engine-scrapers/core").browserScraper;
const { parseSalaryRange, parseHourlyRateToYearly, detectCurrency } = require("@job-engine-scrapers/core").salary;

const TAG_SET = getTagSet();

// ─── Salary parsing (uses shared salary.js functions) ──────────────────

function parseSalary(text) {
  if (!text) return { salary_min: null, salary_max: null, currency: "USD" };

  // Try hourly rate first (has /hr or "per hour" suffix)
  const hourly = parseHourlyRateToYearly(text);
  if (hourly.salary_min !== null || hourly.salary_max !== null) {
    return { salary_min: hourly.salary_min, salary_max: hourly.salary_max, currency: detectCurrency(text) || "USD" };
  }

  // Try range/yearly
  const range = parseSalaryRange(text);
  return {
    salary_min: range.salary_min,
    salary_max: range.salary_max,
    currency: range.currency || detectCurrency(text) || "USD",
  };
}

// ─── SimplyHiredScraper class — extends BrowserScraper ─────────────────

class SimplyHiredScraper extends BrowserScraper {
  get id() { return "simplyhired"; }
  get platform() { return "simplyhired.com"; }

  buildUrl(tag, pageNum) {
    const q = encodeURIComponent(tag);
    return pageNum > 1
      ? `https://www.simplyhired.com/search?q=${q}&pn=${pageNum}`
      : `https://www.simplyhired.com/search?q=${q}`;
  }

  async extractJobs(page, tag, pageNum) {
    // Wait for job cards
    const cardSelectors = [
      '[data-testid="searchSerpJob"]',
      '[class*="SerpJob"]',
      '[class*="job-card"]',
      '[data-testid="search-result"]',
      "li[class*='job']",
      "article",
    ];

    let cardFound = false;
    for (const sel of cardSelectors) {
      const found = await page.$(sel).catch(() => null);
      if (found) {
        await page.waitForSelector(sel, { timeout: 8000 }).catch(() => {
          log.warn(`[${this.id}] Timeout waiting for selector "${sel}" — falling back`);
        });
        cardFound = true;
        break;
      }
    }
    if (!cardFound) {
      log.info(`[${this.id}] No job cards found on page ${pageNum}`);
      return [];
    }

    // Extract cards from rendered DOM
    const cards = await page.evaluate(() => {
      const jobCards = document.querySelectorAll(
        '[data-testid="searchSerpJob"], [class*="SerpJob"], [class*="job-card"], [data-testid="search-result"], li[class*="job"], article'
      );
      return Array.from(jobCards).map((card) => {
        const titleEl = card.querySelector("[data-testid='searchSerpJobTitle'], h2, h3, [class*='title'], a[class*='title']");
        const companyEl = card.querySelector("[data-testid='companyName'], [class*='company'], [class*='employer']");
        const locationEl = card.querySelector("[data-testid='searchSerpJobLocation'], [class*='location']");
        const salaryEl = card.querySelector("[data-testid^='salaryChip'], [class*='salary'], [class*='compensation']");
        const linkEl = titleEl?.closest("a") || titleEl?.querySelector("a") || card.querySelector("a[href*='/job/']");

        return {
          title: titleEl?.textContent?.trim() ?? "",
          company: companyEl?.textContent?.trim() ?? "",
          location: locationEl?.textContent?.trim() ?? "",
          salary: salaryEl?.textContent?.trim() ?? "",
          url: linkEl?.href ?? "",
          text: card.textContent?.slice(0, 1200) ?? "",
        };
      });
    });

    // Save page HTML for this search
    const pageLabel = `search_${tag.replace(/[^a-zA-Z0-9]/g, "_")}_p${pageNum}`;
    const rawPath = saveRawData("simplyhired", pageLabel, await page.content(), "html");
    if (rawPath) {
      log.info(`[${this.id}] Saved raw HTML: ${rawPath}`);
    }

    // Filter and build output objects
    const jobs = [];
    for (const raw of cards) {
      if (!raw.title) continue;

      const rawText = raw.title + " " + raw.text;
      const text = rawText.toLowerCase();
      const tagMatch = matchesAnyTag(TAG_SET, text);
      if (!tagMatch) continue;

      const sal = parseSalary(raw.salary);
      const techStack = extractSkills(rawText);
      const isRemote = /remote/i.test(raw.location || raw.text);

      jobs.push({
        external_id: `simplyhired_${stableId(raw.url || raw.title + raw.company)}`,
        platform: "simplyhired.com",
        title: raw.title,
        company: raw.company || "Unknown",
        url: raw.url || `https://www.simplyhired.com/search?q=${encodeURIComponent(tag)}`,
        salary_min: sal.salary_min,
        salary_max: sal.salary_max,
        currency: sal.currency || "USD",
        contract_type: "B2B",
        location: raw.location || "Remote",
        remote: isRemote,
        skills: [...new Set(techStack)],
        category: "",
        experience_level: "",
        requirements: raw.text.slice(0, 2000),
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

    return jobs;
  }
}

// ─── Main ───────────────────────────────────────────────────────────────

async function main() {
  const scraper = new SimplyHiredScraper({
    maxPages: 3,
    headless: true,
  });

  let result;
  try {
    result = await scraper.scrape();
  } catch (err) {
    if (err.code === "MODULE_NOT_FOUND" || err.message?.includes("Cannot find module 'playwright'")) {
      log.info("Skipped — Playwright not available");
    } else {
      log.error("Fatal:", err.message);
    }
    result = { platform: "simplyhired.com", count: 0, jobs: [] };
  }

  if (result.jobs && result.jobs.length > 0) {
    writeOutput("simplyhired", result.jobs);
    log.info(`${result.jobs.length} matching offers`);
    printTopJobs("[simplyhired]", result.jobs);
  } else {
    log.info("0 matching offers");
  }

  return result;
}

if (require.main === module) {
  main().catch((err) => {
    console.error("[simplyhired] Fatal:", err);
    process.exit(1);
  });
}
module.exports = {
  metadata: {
    id: "simplyhired",
    name: "SimplyHired",
    capabilities: ["browser"],
    needsBrowser: true,
    platform: "simplyhired.com",
    configFields: {
      max_pages: {
        type: "number",
        label: "Max Pages",
        description: "Maximum number of pagination pages to scrape",
        default: 3,
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