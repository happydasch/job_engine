#!/usr/bin/env node
/**
 * Upwork Job Scraper — extends BrowserScraper.
 *
 * Strategy:
 *   1. Uses BrowserScraper base class for stealth Playwright + proxy + fingerprint rotation.
 *   2. Searches Upwork's public search page for each tag, extracting
 *      whatever is visible without authentication.
 */

const { writeOutput, printTopJobs, saveRawData } = require("@job-engine-scrapers/core").output;
const { stableId } = require("@job-engine-scrapers/core").dedup;
const { getTagSet, matchesAnyTag } = require("@job-engine-scrapers/core").tags;
const { extractSkills } = require("@job-engine-scrapers/core").skills;
const { parseHourlyRate } = require("@job-engine-scrapers/core").salary;
const log = require("@job-engine-scrapers/core").logger("upwork");
const config = require("@job-engine-scrapers/core").config;
const BrowserScraper = require("@job-engine-scrapers/core").browserScraper;

const TAG_SET = getTagSet();

// --- UpworkScraper class — extends BrowserScraper -------------------------

class UpworkScraper extends BrowserScraper {
  get id() { return "upwork"; }
  get platform() { return "upwork.com"; }

  buildUrl(tag, pageNum) {
    let url = `https://www.upwork.com/nx/search/jobs/?q=${encodeURIComponent(tag)}&sort=recency`;
    if (pageNum > 1) {
      url += `&page=${pageNum}`;
    }
    return url;
  }

  async detectWaf(page) {
    const baseResult = await super.detectWaf(page);
    if (baseResult) return true;

    try {
      return await page.evaluate(() => {
        const title = document.title;
        const body = document.body?.innerText || "";
        return (
          title.includes("ERROR") ||
          body.includes("cdn-cgi")
        );
      });
    } catch { /* Page evaluate failed — treat as not blocked */
      return false;
    }
  }

  async extractJobs(page, tag, pageNum) {
    log.info(`Searching "${tag}" page ${pageNum}…`);

    // Detect login wall
    const currentUrl = page.url();
    if (currentUrl.includes("/login") || currentUrl.includes("/signup") || currentUrl.includes("ab/account")) {
      log.warn("Sign-in wall detected -- cannot scrape without authentication");
      return [];
    }

    // Wait for job tiles
    await page.waitForSelector(
      '[data-test="JobTile"], [class*="job-tile"], article',
      { timeout: 15000 }
    ).catch(() => {
      log.warn("Timeout waiting for job tiles — falling back");
    });

    const jobs = await page.evaluate(() => {
      const cards = document.querySelectorAll(
        '[data-test="JobTile"], [class*="job-tile"], article[data-test]'
      );
      return Array.from(cards).map((card) => ({
        title: card.querySelector("[class*='title']")?.textContent?.trim() ?? "",
        url: card.querySelector("a")?.href ?? "",
        text: card.textContent?.slice(0, 1000) ?? "",
      }));
    });

    // Save page HTML for this search
    const rawPath = saveRawData("upwork", `search_${tag.replace(/[^a-zA-Z0-9]/g, "_")}`, await page.content(), "html");
    if (rawPath) {
      log.info(`Saved raw HTML: ${rawPath}`);
    }

    return jobs
      .filter((j) => j.title)
      .map((j) => {
        const sal = parseHourlyRate(j.text);
        const skills = extractSkills(j.title + " " + j.text);
        return {
          external_id: `upwork_${j.url && j.url.includes("~") ? j.url.split("~").pop() : stableId(j.url || j.title + (j.company || ""))}`,
          platform: "upwork.com",
          title: j.title,
          company: "Upwork Client",
          url: j.url,
          salary_min: sal.salary_min,
          salary_max: sal.salary_max,
          currency: "USD",
          contract_type: "B2B",
          location: "Remote",
          remote: true,
          skills: skills,
          category: "",
          experience_level: "",
          requirements: "",
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
        };
      })
      .filter((job) => {
        // Filter for tag match
        const text = (job.title + " " + (job.skills ?? []).join(" ")).toLowerCase();
        return matchesAnyTag(TAG_SET, text);
      });
  }
}

// --- Main ---------------------------------------------------------------

async function main() {
  const scraper = new UpworkScraper({ headless: true });
  const result = await scraper.scrape();
  writeOutput("upwork", result.jobs);
  log.info(`${result.count} matching offers`);
  if (result.count === 0) {
    log.info("No results -- this is expected if the site requires login");
  }
  printTopJobs("[Upwork]", result.jobs);
  return result;
}

module.exports = {
  metadata: {
    id: "upwork",
    name: "Upwork",
    capabilities: ["browser"],
    needsBrowser: true,
    platform: "upwork.com",
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
if (require.main === module) main().catch(err => { console.error("[Upwork] Unhandled rejection:", err); process.exit(1); });
