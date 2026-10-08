#!/usr/bin/env node
/**
 * {{displayName}} Scraper — browser-based Playwright scraper.
 *
 * Uses Playwright stealth browser to scrape JavaScript-rendered job listings.
 * TODO: Describe the site's DOM structure, anti-bot measures, pagination, etc.
 */

const proxy = require("@job-engine-scrapers/core").proxy;
const log = require("@job-engine-scrapers/core").logger("{{id}}");
const { humanDelay, humanScroll, createStealthBrowser } = require("@job-engine-scrapers/core").stealth;
const { extractSkills } = require("@job-engine-scrapers/core").skills;
const { writeOutput, printTopJobs, saveRawData } = require("@job-engine-scrapers/core").output;
const { deduplicateByKey, sortBySalary, stableId } = require("@job-engine-scrapers/core").dedup;
const { getTagSet, matchesAnyTag } = require("@job-engine-scrapers/core").tags;
const config = require("@job-engine-scrapers/core").config;

const TAGS = config.getTags();
const TAG_SET = getTagSet();
const SCRAPER_CFG = config.getScraper("{{id}}");
const MAX_PAGES = SCRAPER_CFG ? SCRAPER_CFG.max_pages : 3;

// ─── Page Scraper ──────────────────────────────────────────────────────────

/**
 * Scrape one search page for a given tag.
 * TODO: Adapt selectors and URL structure to the target site.
 */
async function scrapePage(page, tag, pageNum) {
  // TODO: Build the search URL for this tag and page
  const url = `https://{{id}}.com/search?q=${encodeURIComponent(tag)}&page=${pageNum}`;

  log.info(`Searching "${tag}" — page ${pageNum}…`);
  await page.goto(url, { waitUntil: "domcontentloaded", timeout: 20000 });
  await humanDelay();
  await humanScroll(page);

  // Check for WAF/blocking
  const blocked = await page.evaluate(() => {
    const title = document.title.toLowerCase();
    const body = document.body?.innerText?.toLowerCase() || "";
    return title.includes("just a moment") || title.includes("403") || body.includes("cloudflare");
  }).catch(() => false);

  if (blocked) {
    log.info("Blocked by WAF — stopping");
    return [];
  }

  // TODO: Find the correct selector for job cards on the target site
  // Try common selectors, pick the first one that matches
  const cardSelectors = [
    '[class*="job-card"]',
    '[class*="SerpJob"]',
    '[data-testid*="job"]',
    "li[class*='job']",
    "article",
  ];

  let cardFound = false;
  for (const sel of cardSelectors) {
    const found = await page.$(sel).catch(() => null);
    if (found) {
      await page.waitForSelector(sel, { timeout: 8000 }).catch(() => {});
      cardFound = true;
      break;
    }
  }
  if (!cardFound) {
    log.info("No job cards found on page");
    return [];
  }

  await humanDelay();

  // TODO: Extract job data from the DOM
  // This is the most site-specific part — adapt the selectors to the target site
  const jobs = await page.evaluate(() => {
    const cards = document.querySelectorAll(
      '[class*="job-card"], [class*="SerpJob"], [data-testid*="job"], li[class*="job"], article'
    );
    return Array.from(cards).map((card) => {
      const titleEl = card.querySelector("h2, h3, [class*='title'], a[class*='title']");
      const companyEl = card.querySelector("[class*='company'], [class*='employer']");
      const locationEl = card.querySelector("[class*='location']");
      const salaryEl = card.querySelector("[class*='salary'], [class*='compensation']");
      const linkEl = titleEl?.closest("a") || card.querySelector("a[href]");
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

  // Save page HTML for debugging
  const rawPath = saveRawData("{{id}}", `search_${tag}_p${pageNum}`, await page.content(), "html");
  if (rawPath) log.info(`Saved raw HTML: ${rawPath}`);

  return jobs.filter((j) => j.title).map((j) => ({ ...j, _raw: rawPath ? [rawPath] : [] }));
}

// ─── Salary Parsing ────────────────────────────────────────────────────────

/**
 * Parse salary text from the DOM into structured numbers.
 * TODO: Adapt to the target site's salary format.
 */
function parseSalary(text) {
  if (!text) return { salary_min: null, salary_max: null, currency: "USD" };

  let currency = "USD";
  if (text.includes("€")) currency = "EUR";
  else if (text.includes("£")) currency = "GBP";
  else if (text.includes("zł") || text.includes("PLN")) currency = "PLN";

  // Common pattern: "$50k - $100k" or "50,000 - 100,000"
  const range = text.replace(/,/g, "").match(/\$?(\d+[\d.]*(?:k)?)\s*[–—−-]\s*\$?(\d+[\d.]*(?:k)?)/i);
  if (range) {
    let a = parseFloat(range[1]);
    let b = parseFloat(range[2]);
    if (a > 0 && b > 0) {
      // Adjust for 'k' suffix
      if (a < 200 && range[1].includes("k")) a *= 1000;
      if (b < 200 && range[2].includes("k")) b *= 1000;
      // Adjust hourly rates (~2000 hours/year)
      if (a < 200 && b < 200) {
        a = Math.round(a * 2080);
        b = Math.round(b * 2080);
      }
      return { salary_min: Math.round(Math.min(a, b)), salary_max: Math.round(Math.max(a, b)), currency };
    }
  }

  return { salary_min: null, salary_max: null, currency };
}

// ─── Main ──────────────────────────────────────────────────────────────────

async function main() {
  let browser;
  try {
    const proxyUrl = await proxy.getRandomProxyUrl();
    const sb = await createStealthBrowser({ proxyUrl, headless: true });
    browser = sb.browser;
    const page = sb.page;

    const allJobs = new Map();

    for (const tag of TAGS) {
      for (let pageNum = 1; pageNum <= MAX_PAGES; pageNum++) {
        let rawJobs;
        try {
          rawJobs = await scrapePage(page, tag, pageNum);
        } catch (err) {
          log.info(`Error: ${err.message}`);
          break;
        }

        if (rawJobs.length === 0) break;

        for (const job of rawJobs) {
          const text = (job.title + " " + job.text).toLowerCase();
          if (!matchesAnyTag(TAG_SET, text)) continue;

          const sal = parseSalary(job.salary);
          const techStack = extractSkills(text);
          const isRemote = /remote/i.test(job.location || job.text);

          const output = {
            external_id: `{{id}}_${stableId(job.url || job.title + job.company)}`,
            platform: "{{displayName}}",
            title: job.title,
            company: job.company || "Unknown",
            url: job.url || url,
            salary_min: sal.salary_min,
            salary_max: sal.salary_max,
            currency: sal.currency || "USD",
            contract_type: "B2B",
            location: job.location || "Remote",
            remote: isRemote,
            skills: [...new Set(techStack)],
            category: "",
            experience_level: "",
            requirements: job.text.slice(0, 2000),
            discovered_at: new Date().toISOString(),
            nice_to_have_skills: "[]",
            languages: "[]",
            published_at: null,
            expired_at: null,
            working_time: "full_time",
            latitude: null,
            longitude: null,
            street: "",
            _raw: job._raw ?? [],
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
    if (err.code === "MODULE_NOT_FOUND" || err.message?.includes("Cannot find module 'playwright'")) {
      log.info("Skipped — Playwright not available");
    } else {
      log.error("Fatal:", err.message);
    }
    return { platform: "{{displayName}}", count: 0, jobs: [] };
  } finally {
    if (browser) await browser.close().catch(() => {});
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
    capabilities: ["browser"],
    needsBrowser: true,
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