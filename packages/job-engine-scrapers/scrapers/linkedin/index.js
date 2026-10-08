#!/usr/bin/env node
/**
 * LinkedIn Jobs Scraper — uses the public guest job-search API.
 *
 * LinkedIn blocks the authenticated /jobs/search/ page for unauthenticated
 * scraping (it renders a login wall that trips WAF detection). Instead we hit
 * the public "guest" endpoint used by logged-out visitors:
 *
 *   /jobs-guest/jobs/api/seeMoreJobPostings/search
 *
 * This returns a clean server-rendered HTML fragment of job cards, no login
 * required, and paginates via &start=N (step 10).
 *
 * All configuration comes from data/scraper_config.yaml (no env vars).
 *
 * Config (data/scraper_config.yaml):
 *   linkedin:
 *     enabled: true
 *     max_pages: 1               # pages of 10 cards each
 *     location: "Poland"         # location filter; empty = worldwide
 *     seconds_since_posted: 604800  # freshness filter (e.g. 604800 = 7d)
 *     request_delay_ms: 5000     # delay between requests
 *     cookie: "[...]"            # optional: JSON array of cookie objects.
 *                                  supplying a logged-in session raises the
 *                                  guest rate limit, making the scraper more
 *                                  resilient to throttling.
 *     debug: false               # set true to save screenshots + raw HTML
 */

const log = require("@job-engine-scrapers/core").logger("linkedin");
const { extractSkills } = require("@job-engine-scrapers/core").skills;
const { writeOutput, printTopJobs, saveRawData } = require("@job-engine-scrapers/core").output;
const { stableId } = require("@job-engine-scrapers/core").dedup;
const { getTagSet, matchesAnyTag } = require("@job-engine-scrapers/core").tags;
const { parseSalaryRange } = require("@job-engine-scrapers/core").salary;
const config = require("@job-engine-scrapers/core").config;
const BrowserScraper = require("@job-engine-scrapers/core").browserScraper;

const TAG_SET = getTagSet();
const SCRAPER_CFG = config.getScraper("linkedin") || {};
const MAX_PAGES = SCRAPER_CFG.max_pages || 2;

const GUEST_API = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search";
const PAGE_STEP = 10; // guest API returns 10 cards per page

/** Resolve the location filter from scraper config → profile → worldwide. */
function resolveLocation() {
  if (SCRAPER_CFG.location) return SCRAPER_CFG.location;
  try {
    const locs = config.getPreferredLocations ? config.getPreferredLocations() : [];
    if (locs.length > 0) return locs[0];
  } catch { /* ignore — fall through to worldwide */
    // ignore — fall through to worldwide
  }
  return "";
}

const LOCATION = resolveLocation();
const REMOTE_ONLY = (() => {
  try {
    return config.getRemoteOnly();
  } catch { /* ignore — fallback to false */
    return false;
  }
})();

// ─── LinkedinScraper class ──────────────────────────────────────────────

class LinkedinScraper extends BrowserScraper {
  get id() {
    return "linkedin";
  }

  get platform() {
    return "linkedin.com";
  }

  /**
   * Use getSearchTerms() (boosted_keywords from profile, ~20 tags) instead
   * of getTags() (all skills, ~83 tags) to stay within the runner timeout.
   */
  getSearchTags() {
    return config.getSearchTerms();
  }

  /**
   * Override constructor to read request_delay_ms from scraper config.
   */
  constructor(opts) {
    super(opts);
    // Read per-scraper delay from config, falling back to the constructor option
    const cfgDelay = SCRAPER_CFG.request_delay_ms;
    if (cfgDelay != null) this.requestDelayMs = cfgDelay;
  }

  /**
   * Build the guest job-search API URL for a tag and page.
   * Pagination uses &start=N in steps of 10.
   */
  buildUrl(tag, pageNum) {
    const params = new URLSearchParams();
    params.set("keywords", tag);
    if (LOCATION) params.set("location", LOCATION);
    if (REMOTE_ONLY) params.set("f_WT", "2"); // 2 = Remote
    const freshness = Number(SCRAPER_CFG.seconds_since_posted) || 0;
    if (freshness > 0) params.set("f_TPR", `r${freshness}`);
    params.set("start", String((pageNum - 1) * PAGE_STEP));
    return `${GUEST_API}?${params.toString()}`;
  }

  /**
   * Inject optional LinkedIn session cookies from the scraper config to raise
   * the guest rate limit. No-op when cookie is not set.
   */
  async onLaunch() {
    if (this._cookiesApplied) return; // base + scrape both call onLaunch
    this._cookiesApplied = true;

    const raw = SCRAPER_CFG.cookie;
    if (!raw) return; // guest API needs no auth

    let cookies;
    try {
      cookies = JSON.parse(raw);
    } catch { /* Invalid JSON cookie — warn and ignore */
      log.warn("linkedin.cookie is set but contains invalid JSON — ignoring");
      return;
    }
    if (!Array.isArray(cookies)) {
      log.warn("linkedin.cookie must be a JSON array of cookie objects — ignoring");
      return;
    }
    if (!this.page) {
      log.warn("No page available to inject cookies");
      return;
    }

    try {
      await this.page.context().addCookies(
        cookies.map((c) => ({
          name: c.name,
          value: c.value,
          domain: c.domain || ".linkedin.com",
          path: c.path || "/",
        }))
      );
      log.info("Session cookies applied (raises guest rate limit)");
    } catch (err) {
      log.warn(`Failed to apply cookies: ${err.message}`);
    }
  }

  /**
   * Navigate to the guest API URL and detect blocking via HTTP status.
   * LinkedIn returns 429 (rate limited) or 999 (bot block) when throttling.
   * A single retry with backoff is attempted on 429.
   */
  async navigateToPage(page, url) {
    // Pre-navigation delay to respect rate limits
    await new Promise((r) => setTimeout(r, this.requestDelayMs));

    for (let attempt = 1; attempt <= 2; attempt++) {
      let resp;
      try {
        resp = await page.goto(url, { waitUntil: "domcontentloaded", timeout: 15000 });
      } catch (err) {
        log.warn(`[linkedin] Navigation to ${url} failed: ${err.message}`);
        return false;
      }

      const status = resp ? resp.status() : 0;
      if (status === 429 || status === 999) {
        log.warn(`[linkedin] Rate limited (HTTP ${status}) at ${url}`);
        if (attempt === 1) {
          await new Promise((r) => setTimeout(r, 5000 + Math.random() * 5000));
          await this.rotateFingerprint();
          continue;
        }
        return false;
      }
      if (status >= 400) {
        log.warn(`[linkedin] HTTP ${status} at ${url}`);
        return false;
      }

      const blocked = await this.detectWaf(page);
      if (blocked) {
        log.warn(`[linkedin] WAF/auth wall detected at ${url}`);
        if (this.debug) {
          await page.screenshot({ path: `/tmp/linkedin_blocked.png` }).catch(() => {});
        }
        return false;
      }
      return true;
    }
    return false;
  }

  /**
   * Detect a genuine block/challenge. The guest fragment legitimately contains
   * "sign in" chrome, so we only flag real auth-wall redirects and challenges —
   * NOT generic sign-in text (which caused false positives before).
   */
  async detectWaf(page) {
    try {
      const url = page.url().toLowerCase();
      if (url.includes("/authwall") || url.includes("/checkpoint")) return true;
      return await page.evaluate(() => {
        const title = document.title.toLowerCase();
        const html = (document.body?.innerHTML || "").toLowerCase();
        return (
          title.includes("just a moment") ||
          title.includes("security check") ||
          title.includes("attention required") ||
          html.includes("g-recaptcha") ||
          html.includes("cf-challenge") ||
          html.includes("captcha__challenge")
        );
      });
    } catch { /* Page evaluate failed — treat as not blocked */
      return false;
    }
  }

  /**
   * Extract jobs from the guest search-result fragment.
   */
  async extractJobs(page, tag, pageNum) {
    // Guest cards render as <li> containing .base-card / .base-search-card.
    await page
      .waitForSelector("li, div.base-card, div.base-search-card", { timeout: 2000 })
      .catch(() => log.info(`[linkedin] No card selector for "${tag}" p${pageNum}`));

    const rawJobs = await page.evaluate(() => {
      const cards = document.querySelectorAll(
        "li div.base-card, li div.base-search-card, div.base-search-card, div.job-search-card"
      );
      const pick = (el, sels) => {
        for (const s of sels) {
          const found = el.querySelector(s);
          if (found) return found;
        }
        return null;
      };
      return Array.from(cards).map((card) => {
        const titleEl = pick(card, [".base-search-card__title", "h3", "[class*='title']"]);
        const companyEl = pick(card, [".base-search-card__subtitle", "h4", "[class*='subtitle']", "[class*='company']"]);
        const locationEl = pick(card, [".job-search-card__location", "[class*='location']"]);
        const timeEl = pick(card, ["time[datetime]", "time"]);
        const linkEl = pick(card, ["a.base-card__full-link", "a[href*='/jobs/view']", "a[href*='/jobs/']"]);
        const href = linkEl?.href || "";
        const entityUrn = card.getAttribute("data-entity-urn") || "";

        return {
          title: titleEl?.textContent?.trim() ?? "",
          company: companyEl?.textContent?.trim() ?? "",
          location: locationEl?.textContent?.trim() ?? "",
          url: href.split("?")[0],
          jobId:
            (href.match(/\/jobs\/view\/(?:[^/]*-)?(\d+)/) || [])[1] ||
            (entityUrn.match(/(\d+)/) || [])[1] ||
            "",
          datetime: timeEl?.getAttribute("datetime") ?? "",
          text: card.textContent?.replace(/\s+/g, " ").slice(0, 1200) ?? "",
        };
      });
    });

    const rawPath = this.debug ? await this._saveRawData(page, tag, pageNum) : null;

    const jobs = [];
    let dropped = 0;
    for (const job of rawJobs) {
      if (!job.title) continue;

      const rawText = `${job.title} ${job.company} ${job.text}`;
      if (!matchesAnyTag(TAG_SET, rawText.toLowerCase())) {
        dropped++;
        continue;
      }

      const sal = parseSalaryRange(job.text);
      const techStack = extractSkills(rawText);
      const isRemote = /remote/i.test(job.location) || /remote/i.test(job.text);
      const idSeed = job.jobId || job.url || `${job.title}${job.company}`;

      jobs.push({
        external_id: `linkedin_${job.jobId || stableId(idSeed)}`,
        platform: "linkedin.com",
        title: job.title,
        company: job.company || "Unknown",
        url: job.url || this.buildUrl(tag, pageNum),
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
        published_at: parseDatetime(job.datetime),
        expired_at: null,
        last_published_at: null,
        working_time: "full_time",
        latitude: null,
        longitude: null,
        street: "",
        _raw: rawPath ? [rawPath] : [],
      });
    }

    if (dropped > 0) log.info(`[linkedin] "${tag}" p${pageNum}: ${jobs.length} kept, ${dropped} off-tag`);
    return jobs;
  }

  /**
   * Save the guest fragment as raw HTML for a search.
   */
  async _saveRawData(page, tag, pageNum) {
    try {
      const rawPath = saveRawData(
        "linkedin",
        `search_${tag.replace(/[^a-zA-Z0-9]/g, "_")}_page_${pageNum}`,
        await page.content(),
        "html"
      );
      if (rawPath) log.info(`Saved raw HTML: ${rawPath}`);
      return rawPath;
    } catch { /* Save failure is non-critical — return null */
      return null;
    }
  }
}

/** Convert a LinkedIn <time datetime="YYYY-MM-DD"> value to an ISO string. */
function parseDatetime(dt) {
  if (!dt) return null;
  const d = new Date(dt);
  return isNaN(d.getTime()) ? null : d.toISOString();
}

// ─── Main ───────────────────────────────────────────────────────────────

async function main() {
  const scraper = new LinkedinScraper({
    maxPages: MAX_PAGES,
    headless: true,
    blockResources: true, // no need for logos/fonts on the guest fragment
    humanBehavior: false, // guest API fragment doesn't need human mimicry
  });
  const result = await scraper.scrape();
  if (result.jobs.length > 0) {
    writeOutput("linkedin", result.jobs);
    log.info(`→ ${result.jobs.length} matching offers`);
    printTopJobs("[linkedin]", result.jobs);
  }
  return result;
}

if (require.main === module) {
  main().catch((err) => {
    console.error("[linkedin] Fatal:", err);
    process.exit(1);
  });
}
module.exports = {
  metadata: {
    id: "linkedin",
    name: "LinkedIn",
    capabilities: ["browser"],
    needsBrowser: true,
    platform: "linkedin.com",
    configFields: {
      max_pages: {
        type: "number",
        label: "Max Pages",
        description: "Maximum number of pagination pages to scrape (10 jobs each)",
        default: 2,
        min: 1,
        max: 100,
        unit: "pages",
      },
      location: {
        type: "string",
        label: "Location",
        description: "Location filter (e.g. \"Poland\"). Empty = worldwide.",
        default: "",
      },
      seconds_since_posted: {
        type: "number",
        label: "Freshness (seconds)",
        description: "Only jobs posted within N seconds (0 = any). 604800 = 7 days.",
        default: 0,
        min: 0,
        max: 2592000,
        unit: "seconds",
      },
      request_delay_ms: {
        type: "number",
        label: "Request Delay (ms)",
        description: "Delay between requests to avoid rate limiting.",
        default: 5000,
        min: 1000,
        max: 60000,
        unit: "ms",
      },
      cookie: {
        type: "password",
        label: "Session Cookie",
        description: "Optional: JSON array of LinkedIn session cookie objects. Raises the guest rate limit for more resilient scraping.",
        default: "",
        placeholder: '[{"name":"...","value":"...","domain":".linkedin.com"}]',
      },
      debug: {
        type: "boolean",
        label: "Debug Mode",
        description: "Save screenshots on failure and raw HTML pages to disk.",
        default: false,
      },
    },
  },
  main,
  register(registry) {
    registry.register(this);
  },
};
