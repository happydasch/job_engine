#!/usr/bin/env node
/**
 * Arc.dev Scraper — fetch-based (SSR Next.js HTML).
 *
 * Parses __NEXT_DATA__ JSON embedded in arc.dev/remote-jobs pages.
 *
 * Arc renders two job lists server-side into
 * __NEXT_DATA__.props.pageProps:
 *   - arcJobs[]       → "Arc Exclusive" listings WITH real detail pages
 *                       (/remote-jobs/details/{urlString}-{randomKey}, HTTP 200)
 *                       and rich data (salary, experience, timezone, skills).
 *   - externalJobs[]  → aggregated 3rd-party postings that have NO arc detail
 *                       page (detail path 404s) and carry no source/apply URL,
 *                       so they cannot be linked reliably → intentionally skipped.
 *
 * Coverage strategy: no client-side pagination API exists (list is virtualized
 * from the SSR payload), so we fetch the base page plus one skill-category page
 * per configured search term (/remote-jobs/{slug}). Each page yields up to ~20
 * exclusive jobs; results are deduped by randomKey.
 *
 * Data fields (arcJobs[]):
 *   randomKey, title, jobType (contract|permanent), jobRole, experienceLevel
 *   (mid|senior|…), urlString, postedAt (unix seconds), minAnnualSalary,
 *   maxAnnualSalary, minHourlyRate, maxHourlyRate, timeZone, requiredCountries[],
 *   categories[] ({name, urlString}).
 */

const log = require("@job-engine-scrapers/core").logger("arcdev");
const { fetchResult, delay } = require("@job-engine-scrapers/core").fetch;
const { writeOutput, printTopJobs, saveRawData } = require("@job-engine-scrapers/core").output;
const { deduplicateByKey, sortBySalary, stableId } = require("@job-engine-scrapers/core").dedup;
const { getTagSet, matchesAnyTag } = require("@job-engine-scrapers/core").tags;
const { extractSkills } = require("@job-engine-scrapers/core").skills;
const config = require("@job-engine-scrapers/core").config;

const BASE_URL = "https://arc.dev";
const LIST_URL = `${BASE_URL}/remote-jobs`;
const HOURS_PER_YEAR = 2080; // 40h × 52w — matches core salary.parseHourlyRateToYearly

const TAG_SET = getTagSet();
const SCRAPER_CFG = config.getScraper("arcdev") || {};
// Cap how many skill-category pages we fetch on top of the base page.
const MAX_CATEGORIES = SCRAPER_CFG.max_categories ?? 20;
const REQUEST_DELAY_MS = SCRAPER_CFG.request_delay_ms ?? 800;

// ——————————————————————————————————————————————————————————————————————————
//  Parse arcJobs[] out of __NEXT_DATA__
// ——————————————————————————————————————————————————————————————————————————

function parseArcJobs(html) {
  const match = html.match(
    /<script id="__NEXT_DATA__"[^>]*type="application\/json"[^>]*>([\s\S]*?)<\/script>/
  );
  if (!match) return null;
  try {
    const data = JSON.parse(match[1]);
    const pp = data.props?.pageProps ?? {};
    return {
      arcJobs: Array.isArray(pp.arcJobs) ? pp.arcJobs : [],
      externalCount: Array.isArray(pp.externalJobs) ? pp.externalJobs.length : 0,
    };
  } catch { /* Invalid JSON from __NEXT_DATA__ — return null */
    return null;
  }
}

// ——————————————————————————————————————————————————————————————————————————
//  Field mapping helpers
// ——————————————————————————————————————————————————————————————————————————

/** Annual salary preferred; fall back to hourly rate × 2080. */
function resolveSalary(j) {
  if (typeof j.minAnnualSalary === "number" || typeof j.maxAnnualSalary === "number") {
    return {
      salary_min: j.minAnnualSalary ?? null,
      salary_max: j.maxAnnualSalary ?? null,
      currency: "USD",
    };
  }
  if (typeof j.minHourlyRate === "number" || typeof j.maxHourlyRate === "number") {
    return {
      salary_min: j.minHourlyRate != null ? Math.round(j.minHourlyRate * HOURS_PER_YEAR) : null,
      salary_max: j.maxHourlyRate != null ? Math.round(j.maxHourlyRate * HOURS_PER_YEAR) : null,
      currency: "USD",
    };
  }
  return { salary_min: null, salary_max: null, currency: "USD" };
}

/** Arc jobType → the project's contract_type vocabulary. */
function mapContractType(jobType) {
  switch ((jobType || "").toLowerCase()) {
    case "contract":
    case "freelance":
      return "B2B";
    case "permanent":
      return "Permanent";
    default:
      return "B2B";
  }
}

function mapArcJob(j, rawPaths) {
  const title = (j.title || "").trim();
  const randomKey = j.randomKey || "";
  const urlString = j.urlString || "";
  if (!title || !randomKey || !urlString) return null;

  const categoryNames = Array.isArray(j.categories)
    ? j.categories.map((c) => c?.name).filter(Boolean)
    : [];

  const rawText = [title, j.jobRole, categoryNames.join(" ")].filter(Boolean).join(" ");
  const techStack = extractSkills(rawText);
  // Category-targeted fetches are already relevant, but keep the profile filter
  // consistent with the other scrapers.
  if (!matchesAnyTag(TAG_SET, rawText.toLowerCase()) && techStack.length === 0) return null;

  const { salary_min, salary_max, currency } = resolveSalary(j);

  // Arc lists exclusive jobs by required regions rather than a single city.
  const countries = Array.isArray(j.requiredCountries) ? j.requiredCountries : [];
  const location = countries.length > 0 ? countries.join(", ") : "Remote";

  const requirements = [
    j.timeZone ? `Time zone: ${j.timeZone}` : "",
    j.clientTimeZoneRestriction ? `Overlap: ${j.clientTimeZoneRestriction}` : "",
    countries.length ? `Regions: ${countries.join(", ")}` : "",
  ].filter(Boolean).join(" | ");

  const skills = techStack.length > 0 ? techStack : categoryNames;

  return {
    external_id: `arcdev_${randomKey}`,
    platform: "arc.dev",
    title,
    company: "Unknown", // Arc withholds exclusive-client names in listing data.
    url: `${BASE_URL}/remote-jobs/details/${urlString}-${randomKey}`,
    salary_min,
    salary_max,
    currency,
    contract_type: mapContractType(j.jobType),
    location,
    remote: true,
    skills: [...new Set(skills)],
    category: (j.jobRole || "").replace(/_/g, " "),
    experience_level: j.experienceLevel || "",
    requirements,
    discovered_at: new Date().toISOString(),
    nice_to_have_skills: "[]",
    languages: "[]",
    published_at: typeof j.postedAt === "number"
      ? new Date(j.postedAt * 1000).toISOString()
      : null,
    expired_at: null,
    last_published_at: null,
    working_time: "full_time",
    latitude: null,
    longitude: null,
    street: "",
    _raw: rawPaths,
  };
}

// ——————————————————————————————————————————————————————————————————————————
//  Category slugs from configured search terms
// ——————————————————————————————————————————————————————————————————————————

/** Arc category slug — lowercase, non-alphanumerics collapsed to single hyphen. */
function toCategorySlug(term) {
  return term
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

function buildTargets() {
  const terms = config.getSearchTerms();
  const slugs = [];
  const seen = new Set();
  for (const term of terms) {
    const slug = toCategorySlug(term);
    if (!slug || seen.has(slug)) continue;
    seen.add(slug);
    slugs.push(slug);
    if (slugs.length >= MAX_CATEGORIES) break;
  }
  // Base page first (newest across all roles), then per-skill category pages.
  return [
    { label: "base", url: LIST_URL },
    ...slugs.map((slug) => ({ label: slug, url: `${LIST_URL}/${slug}` })),
  ];
}

// ——————————————————————————————————————————————————————————————————————————
//  Main
// ——————————————————————————————————————————————————————————————————————————

async function main() {
  const targets = buildTargets();
  log.info(`Fetching ${targets.length} arc.dev page(s) (1 base + ${targets.length - 1} categories)…`);

  const jobs = [];
  const rawPaths = [];
  let skippedExternal = 0;

  for (let i = 0; i < targets.length; i++) {
    const { label, url } = targets[i];
    if (i > 0) await delay(REQUEST_DELAY_MS);

    const result = await fetchResult(url);
    if (!result.ok) {
      log.warn(`HTTP ${result.status}${result.error ? `: ${result.error}` : ""} — ${url}`);
      continue;
    }

    const html = result.body;
    if (html.includes("Just a moment") || html.includes("Attention Required! | Cloudflare")) {
      log.warn(`Blocked by WAF — ${url}`);
      continue;
    }

    const rawPath = saveRawData("arcdev", `page_${label}`, html, "html");
    if (rawPath) rawPaths.push(rawPath);

    const parsed = parseArcJobs(html);
    if (!parsed) {
      log.warn(`No __NEXT_DATA__ found — site structure may have changed (${url})`);
      continue;
    }

    skippedExternal += parsed.externalCount;
    let matched = 0;
    for (const raw of parsed.arcJobs) {
      const job = mapArcJob(raw, rawPath ? [rawPath] : []);
      if (job) { jobs.push(job); matched++; }
    }
    log.info(`[${label}] ${parsed.arcJobs.length} exclusive jobs → ${matched} matched`);
  }

  if (skippedExternal > 0) {
    log.info(`Skipped ${skippedExternal} external listing(s) — no reachable arc detail URL`);
  }

  const matches = sortBySalary(deduplicateByKey(jobs, (j) => j.external_id));
  writeOutput("arcdev", matches);

  log.info(`→ ${matches.length} matching offers`);
  printTopJobs("[Arc.dev]", matches);

  return { platform: "arc.dev", count: matches.length, jobs: matches };
}

module.exports = {
  metadata: {
    id: "arcdev",
    name: "Arc.dev",
    capabilities: ["fetch"],
    needsBrowser: false,
    platform: "arc.dev",
    configFields: {
      max_categories: {
        type: "number",
        label: "Max Categories",
        description: "How many skill-category pages to fetch (in addition to the base page)",
        default: 20,
        min: 0,
        max: 100,
        step: 1,
        unit: "pages",
      },
      request_delay_ms: {
        type: "number",
        label: "Request Delay (ms)",
        description: "Delay between page requests to stay polite",
        default: 800,
        min: 0,
        max: 10000,
        step: 100,
        unit: "ms",
      },
    },
  },
  main,
  register(registry) {
    registry.register(this);
  },
};
if (require.main === module) main().catch(err => { console.error("[Arc.dev] Unhandled rejection:", err); process.exit(1); });
