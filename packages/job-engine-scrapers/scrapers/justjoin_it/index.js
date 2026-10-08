#!/usr/bin/env node
/**
 * JustJoin.it Scraper — API-first with Playwright browser fallback.
 *
 * Fetches job listings from JustJoin.it's public API and filters
 * for matching tags. Accepts all contract types (not just B2B) and
 * picks the best salary across available employment types.
 * Tags are read from my_profile.yaml (via config.js).
 * Falls back to browser-based scraping when the API is down or returns
 * empty results.
 */

const log = require("@job-engine-scrapers/core").logger("justjoin_it");
const { fetchJson, fetchHtml } = require("@job-engine-scrapers/core").fetch;
const { writeOutput, printTopJobs, saveRawData } = require("@job-engine-scrapers/core").output;
const { deduplicateByKey, sortBySalary, stableId } = require("@job-engine-scrapers/core").dedup;
const { getTagSet, matchesAnyTag } = require("@job-engine-scrapers/core").tags;
const { extractSkills } = require("@job-engine-scrapers/core").skills;
const config = require("@job-engine-scrapers/core").config;

const CANDIDATE_API = "https://justjoin.it/api/candidate-api/offers";

// Cache tags once at module load
const TAGS = config.getTags();
const TAG_SET = getTagSet();
const SCRAPER_CFG = config.getScraper("justjoin_it");
const MAX_PAGES = SCRAPER_CFG ? SCRAPER_CFG.max_pages : 20;

// How many job-description pages to fetch at once. Keep modest to stay polite.
const DESCRIPTION_CONCURRENCY = SCRAPER_CFG?.description_concurrency || 5;

// Preference order for contract types (higher index = preferred)
const CONTRACT_PREFERENCE = ["mandate", "contract", "permanent", "b2b"];
// Preference order for pay units: monthly > hourly > daily
const UNIT_SCORE = { month: 3, monthly: 3, day: 1, daily: 1, hour: 2, hourly: 2 };

// ——————————————————————————————————————————————————————————————————————————
//  API Fetch & filter
// ——————————————————————————————————————————————————————————————————————————

async function fetchPage(pageNum) {
  const cursor = pageNum * 10;
  const url = `${CANDIDATE_API}?cursor=${cursor}`;
  const body = await fetchJson(url, {}, "JustJoin.it");
  if (!body) {
    log.warn(`No data from API — page ${pageNum} done`);
    return { items: [], done: true };
  }

  // Save raw API response
  const rawPath = saveRawData("justjoin_it", `page_${pageNum}`, body, "json");
  if (rawPath) {
    log.info(`Saved raw data: ${rawPath}`);
  }

  const items = body.data ?? [];
  // Attach raw path to each item
  for (const item of items) {
    if (rawPath) item._raw = [rawPath];
  }
  return { items, done: items.length === 0 };
}

/**
 * Check if a job matches any of the user's tags.
 * Matches against title, category key, and required skills (OR logic).
 * No longer restricted to B2B-only — all contract types are accepted.
 */
function isMatch(item) {
  const title = (item.title ?? "").toLowerCase();
  const category = (item.category?.key ?? "").toLowerCase();
  const skills = (item.requiredSkills ?? []).map((s) => (s.name ?? "").toLowerCase());
  const allText = title + " " + category + " " + skills.join(" ");

  // Match any tag in title, category, or skills
  return matchesAnyTag(TAG_SET, allText);
}

/**
 * Pick the best salary across all available employment types.
 * Preference: B2B > permanent > mandate/contract
 * Within same type: monthly > hourly > daily
 * Falls back to first type with a salary if none match preferences.
 */
function pickBestSalary(employmentTypes) {
  if (!Array.isArray(employmentTypes) || employmentTypes.length === 0) {
    return { salary_min: null, salary_max: null, currency: "PLN", contract_type: null };
  }

  let best = null;
  let bestScore = -1;

  for (const et of employmentTypes) {
    const typeStr = (et.type ?? "").toLowerCase();
    const unitStr = (et.unit ?? "").toLowerCase();
    const typeIdx = CONTRACT_PREFERENCE.indexOf(typeStr);
    if (typeIdx === -1) continue; // skip unknown types

    const unitScore = UNIT_SCORE[unitStr] ?? 0;
    // Score: type preference dominates, unit preference breaks ties
    const score = typeIdx * 10 + unitScore;

    // Skip if this entry has no salary data
    const fromVal = et.from ?? et.fromPerUnit ?? null;
    const toVal = et.to ?? et.toPerUnit ?? null;
    if (fromVal == null && toVal == null) continue;

    if (score > bestScore) {
      bestScore = score;
      best = {
        salary_min: fromVal,
        salary_max: toVal,
        currency: et.currency ?? "PLN",
        contract_type: typeStr,
      };
    }
  }

  return best ?? { salary_min: null, salary_max: null, currency: "PLN", contract_type: null };
}

function parseItem(item) {
  const sal = pickBestSalary(item.employmentTypes);
  const workplace = (item.workplaceType ?? "").toLowerCase();
  const city = item.city ?? "";

  let location = "Remote";
  if (workplace === "hybrid" && city) location = `Hybrid / ${city}`;
  else if (workplace === "office") location = city || "Office";
  else if (workplace === "remote") location = "Remote";
  else if (city) location = city;

  return {
    external_id: `justjoin_${item.guid}`,
    platform: "justjoin.it",
    title: item.title ?? "Unknown",
    company: item.companyName ?? "Unknown",
    url: item.slug
      ? `https://justjoin.it/job-offer/${item.slug}`
      : `https://justjoin.it/offers/${item.guid}`,
    salary_min: sal.salary_min,
    salary_max: sal.salary_max,
    currency: sal.currency,
    contract_type: sal.contract_type ?? "b2b",
    location,
    remote: workplace === "remote",
    skills: (item.requiredSkills ?? []).map((s) => (s.name ?? "").trim()),
    category: item.category?.key ?? "",
    experience_level: item.experienceLevel ?? "",
    requirements: "",
    discovered_at: new Date().toISOString(),

    // === NEW FIELDS ===
    // Nice-to-have skills (bonus for matching)
    nice_to_have_skills: JSON.stringify((item.niceToHaveSkills ?? []).map(s => (s.name ?? "").trim())),

    // Language requirements
    languages: JSON.stringify((item.languages ?? []).map(l => ({ code: l.code, level: l.level }))),

    // Timestamps
    published_at: item.publishedAt ?? null,
    expired_at: item.expiredAt ?? null,
    last_published_at: item.lastPublishedAt ?? null,

    // Work info
    working_time: item.workingTime ?? "full_time",

    // Geo
    latitude: item.latitude ?? null,
    longitude: item.longitude ?? null,
    street: item.street ?? "",

    // Raw data refs
    _raw: item._raw ?? [],
  };
}

// ——————————————————————————————————————————————————————————————————————————
//  Description enrichment (JSON-LD from each offer page)
// ——————————————————————————————————————————————————————————————————————————

async function fetchDescription(job) {
  try {
    const html = await fetchHtml(job.url, "[JustJoin.it]", { maxRetries: 1 });
    if (!html) return;

    // Save raw HTML response
    const rawPath = saveRawData("justjoin_it", `desc_${job.external_id}`, html, "html");
    if (rawPath) {
      if (!job._raw) job._raw = [];
      job._raw.push(rawPath);
    }

    const jsonldMatch = html.match(
      /<script[^>]*type="application\/ld\+json"[^>]*>([\s\S]*?)<\/script>/
    );
    if (!jsonldMatch) return;
    const ld = JSON.parse(jsonldMatch[1]);
    // Could be top-level or nested in @graph
    const data = ld["@graph"]
      ? ld["@graph"].find((g) => g["@type"] === "JobPosting")
      : ld;
    if (data && data.description) {
      job.requirements = data.description;
    }
  } catch { /* Invalid JSON-LD — skip */
    log.warn(`Failed to parse description from JSON-LD for ${job?.title || "unknown"}`);
  }
}

/**
 * Fetch descriptions for all jobs with a fixed concurrency limit (worker pool).
 */
async function fetchDescriptions(jobs, concurrency) {
  let cursor = 0;
  async function worker() {
    while (cursor < jobs.length) {
      const job = jobs[cursor++];
      await fetchDescription(job);
    }
  }
  const workers = Array.from({ length: Math.max(1, concurrency) }, () => worker());
  await Promise.all(workers);
}

// ——————————————————————————————————————————————————————————————————————————
//  Browser fallback (when API is down)
// ——————————————————————————————————————————————————————————————————————————

async function scrapeViaBrowser() {
  log.info("API unavailable — trying browser fallback…");
  try {
    const { createStealthBrowser, humanDelay, humanScroll } = require("@job-engine-scrapers/core").stealth;
    const proxy = require("@job-engine-scrapers/core").proxy;
    const proxyUrl = await proxy.getRandomProxyUrl();
    const sb = await createStealthBrowser({ proxyUrl, headless: true });
    const browser = sb.browser;
    const page = sb.page;

    await page.goto(`https://justjoin.it/offers?remote=yes`, { waitUntil: "networkidle", timeout: 30000 });
    await humanDelay();

    // Scroll-based collection (from job-scraper-main pattern)
    const jobs = await page.evaluate(() => {
      // Scroll to bottom to trigger lazy loading
      let totalHeight = 0;
      const scrollStep = 800;
      const maxScroll = 5000;
      while (totalHeight < maxScroll) {
        window.scrollBy(0, scrollStep);
        totalHeight += scrollStep;
      }

      // Collect job cards using selectors from job-scraper-main
      const cards = document.querySelectorAll(
        '[data-test="offers-list-item"], [class*="offer-card"], [class*="posting-item"], article, .css-2crog7'
      );
      const seen = new Set();
      return Array.from(cards).filter(card => {
        const key = card.textContent?.slice(0, 80) || "";
        if (seen.has(key)) return false;
        seen.add(key);
        return true;
      }).map((card) => ({
        title: card.querySelector('[class*="title"], h2, h3')?.textContent?.trim() ?? "",
        company: card.querySelector('[class*="company"], [class*="employer"]')?.textContent?.trim() ?? "",
        salary: card.querySelector('[class*="salary"], [class*="price"]')?.textContent?.trim() ?? "",
        url: card.querySelector("a")?.href ?? "",
        // Date extraction from job-scraper-main: div.css-1am4i4o
        dateText: card.querySelector("div.css-1am4i4o, [class*='date'], [class*='posted']")?.textContent?.trim() ?? "",
        text: card.textContent?.slice(0, 800) ?? "",
      }));
    });

    await browser.close();

    return jobs
      .filter((j) => j.title && matchesAnyTag(TAG_SET, j.title.toLowerCase()))
      .map((j) => {
        // Parse date from job-scraper-main pattern: "New" = fresh, "Xd" = X days
        let publishedAt = null;
        if (j.dateText) {
          const dt = j.dateText.trim().toLowerCase();
          if (dt === "new" || dt.includes("today") || dt.includes("godzin")) {
            // Fresh — leave null (current)
          } else {
            const dayMatch = dt.match(/(\d+)d/);
            if (dayMatch) {
              const daysAgo = parseInt(dayMatch[1], 10);
              if (daysAgo <= 30) {
                const d = new Date();
                d.setDate(d.getDate() - daysAgo);
                publishedAt = d.toISOString();
              }
            }
          }
        }

        return {
          external_id: `justjoin_browser_${stableId(j.url)}`,
          platform: "justjoin.it",
          title: j.title,
          company: j.company || "Unknown",
          url: j.url,
          salary_min: null,
          salary_max: null,
          currency: "PLN",
          contract_type: "B2B",
          location: "Remote",
          remote: true,
          skills: extractSkills(j.text),
          category: "",
          experience_level: "",
          requirements: "",
          discovered_at: new Date().toISOString(),

          // === NEW FIELDS ===
          nice_to_have_skills: "[]",
          languages: "[]",
          published_at: publishedAt,
          expired_at: null,
          last_published_at: null,
          working_time: "full_time",
          latitude: null,
          longitude: null,
          street: "",
          _raw: [],
        };
      });
  } catch (err) {
    log.warn(`Browser fallback also failed: ${err.message}`);
    return [];
  }
}

// ——————————————————————————————————————————————————————————————————————————
//  Main
// ——————————————————————————————————————————————————————————————————————————

async function main() {
  const allItems = [];

  for (let page = 0; page < MAX_PAGES; page++) {
    const { items, done } = await fetchPage(page);
    if (done) break;
    allItems.push(...items);
  }

  let jobs = [];
  if (allItems.length > 0) {
    log.info(`Fetched ${allItems.length} items via API`);

    const matches = allItems.filter(isMatch).map(parseItem);

    // Deduplicate + sort
    const dedupedJobs = sortBySalary(deduplicateByKey(matches, (j) => j.external_id));
    jobs = dedupedJobs;

    log.info(`→ ${jobs.length} unique matching offers (from ${matches.length} raw matches)`);

    // Fetch descriptions from each job's page (JSON-LD), bounded-concurrent
    // instead of strictly serial (was N sequential round-trips + 200ms each).
    log.info(`Fetching ${jobs.length} job descriptions…`);
    await fetchDescriptions(jobs, DESCRIPTION_CONCURRENCY);
  } else {
    // API returned nothing — try browser fallback
    jobs = await scrapeViaBrowser();
    log.info(`Browser fallback → ${jobs.length} jobs`);
  }

  // Sort + write
  jobs = sortBySalary(jobs);
  writeOutput("justjoin_it", jobs);

  printTopJobs("[JustJoin.it]", jobs);

  return { platform: "justjoin.it", count: jobs.length, jobs };
}

if (require.main === module) {
  main().catch((err) => {
    console.error("[JustJoin.it] Fatal:", err);
    process.exit(1);
  });
}
module.exports = {
  metadata: {
    id: "justjoin_it",
    name: "JustJoin.it",
    capabilities: ["api"],
    needsBrowser: false,
    platform: "justjoin.it",
    configFields: {
      max_pages: {
        type: "number",
        label: "Max Pages",
        description: "Maximum number of pagination pages to scrape (10 items/page)",
        default: 20,
        min: 1,
        max: 100,
        unit: "pages",
      },
      description_concurrency: {
        type: "number",
        label: "Description Concurrency",
        description: "Number of concurrent description detail fetches",
        default: 5,
        min: 1,
        max: 20,
        unit: "requests",
      },
    },
  },
  main,
  register(registry) {
    registry.register(this);
  },
};