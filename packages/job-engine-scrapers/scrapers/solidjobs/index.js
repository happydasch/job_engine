#!/usr/bin/env node
/**
 * Solid Jobs Scraper — direct public API.
 *
 * Fetches IT offers from https://solid.jobs/public-api/offers/IT
 * (no auth required) and filters for B2B + matching tags.
 * Captures ALL available API fields for maximum data quality.
 */

const proxy = require("@job-engine-scrapers/core").proxy;
const log = require("@job-engine-scrapers/core").logger("solidjobs");
const { fetchJson } = require("@job-engine-scrapers/core").fetch;
const { writeOutput, printTopJobs, saveRawData } = require("@job-engine-scrapers/core").output;
const { deduplicateByKey, sortBySalary } = require("@job-engine-scrapers/core").dedup;
const { getTagSet, matchesAnyTag } = require("@job-engine-scrapers/core").tags;
const config = require("@job-engine-scrapers/core").config;

const API_BASE = "https://solid.jobs/public-api/offers/IT";

// Cache config once at module load
const TAGS = config.getTags();
const TAG_SET = getTagSet();
const SCRAPER_CFG = config.getScraper("solidjobs");
const MAX_PAGES = SCRAPER_CFG ? SCRAPER_CFG.max_pages ?? 10 : 10;

// ——————————————————————————————————————————————————————————————————————————
//  Helpers
// ——————————————————————————————————————————————————————————————————————————

/**
 * Minimal HTML-to-text converter for job descriptions.
 * Handles common block elements and HTML entities.
 */
function stripHtml(html) {
  if (!html) return "";
  return html
    .replace(/<br\s*\/?>/gi, "\n")
    .replace(/<\/p>/gi, "\n\n")
    .replace(/<\/li>/gi, "\n")
    .replace(/<\/tr>/gi, "\n")
    .replace(/<\/h[1-6]>/gi, "\n\n")
    .replace(/<\/div>/gi, "\n")
    .replace(/<[^>]*>/g, "")
    .replace(/&nbsp;/g, " ")
    .replace(/&amp;/g, "&")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
    .replace(/&#x27;/gi, "'")
    .replace(/\u00A0/g, " ")
    .replace(/[ \t]+/g, " ")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

// ——————————————————————————————————————————————————————————————————————————
//  API Fetch
// ——————————————————————————————————————————————————————————————————————————

async function fetchPage(pageIndex) {
  const url = `${API_BASE}?campaign=job-scraper&pageSize=500&pageIndex=${pageIndex}`;
  const body = await fetchJson(url, {}, "[solidjobs]");
  if (!body) {
    log.warn(`No data from API — page ${pageIndex} done`);
    return { jobs: [], done: true };
  }

  // Save raw API response
  const rawPath = saveRawData("solidjobs", `page_${pageIndex}`, body, "json");
  if (rawPath) {
    log.info(`Saved raw data: ${rawPath}`);
  }

  const jobs = body.jobs ?? [];
  // Attach raw data path to each job for traceability
  for (const job of jobs) {
    if (rawPath) {
      job._raw = [rawPath];
    }
  }

  log.info(`Fetching page ${pageIndex}: ${jobs.length} offers`);
  return {
    jobs,
    done: jobs.length === 0 || pageIndex >= (body.totalPages ?? 1) - 1,
    totalCount: body.totalCount ?? 0,
    totalPages: body.totalPages ?? 1,
  };
}

// ——————————————————————————————————————————————————————————————————————————
//  Filtering
// ——————————————————————————————————————————————————————————————————————————

/**
 * Check if a job has a B2B salary (primary or secondary).
 * Returns the B2B salary object or null.
 */
function getB2BSalary(job) {
  const salary = job.salary ?? {};
  if (
    salary.employmentType &&
    salary.employmentType.toLowerCase() === "b2b"
  ) {
    return salary;
  }

  const secondary = job.secondarySalary ?? {};
  if (
    secondary.employmentType &&
    secondary.employmentType.toLowerCase() === "b2b"
  ) {
    return secondary;
  }

  return null;
}

/**
 * Get secondary salary info, correctly handling the case where
 * B2B is the secondary salary (swap primary/secondary).
 */
function getSecondarySalaryInfo(job) {
  const salary = job.salary ?? {};
  const secondary = job.secondarySalary ?? {};

  // Primary is already B2B → secondary is the alternative contract
  if (salary.employmentType?.toLowerCase() === "b2b" && secondary?.employmentType) {
    return {
      salary_min: secondary.from ?? null,
      salary_max: secondary.to ?? null,
      currency: secondary.currency ?? null,
      contract_type: secondary.employmentType ?? null,
    };
  }

  // Secondary is B2B → the "primary" salary is actually the alternative contract
  if (secondary?.employmentType?.toLowerCase() === "b2b" && salary?.employmentType) {
    return {
      salary_min: salary.from ?? null,
      salary_max: salary.to ?? null,
      currency: salary.currency ?? null,
      contract_type: salary.employmentType ?? null,
    };
  }

  // Neither is B2B (shouldn't happen due to B2B filter, but be safe)
  if (secondary?.employmentType) {
    return {
      salary_min: secondary.from ?? null,
      salary_max: secondary.to ?? null,
      currency: secondary.currency ?? null,
      contract_type: secondary.employmentType ?? null,
    };
  }

  // No secondary salary at all
  return {
    salary_min: null,
    salary_max: null,
    currency: null,
    contract_type: null,
  };
}

/**
 * Check if a job matches any search tag.
 * A match occurs if ANY tag appears in:
 *   - title (lowercased)
 *   - category or subCategory (lowercased)
 *   - any skill name (lowercased)
 *   - description text (lowercased, HTML-stripped)
 */
function isMatch(job) {
  const title = (job.title ?? "").toLowerCase();
  const category = (job.category ?? "").toLowerCase();
  const subCategory = (job.subCategory ?? "").toLowerCase();
  const skills = (job.skills ?? []).map((s) => (s.name ?? "").toLowerCase());
  const description = stripHtml(job.description ?? "").toLowerCase();
  const searchText = [title, category, subCategory, ...skills, description].join(" ");
  return matchesAnyTag(TAG_SET, searchText);
}

// ——————————————————————————————————————————————————————————————————————————
//  Parsing
// ——————————————————————————————————————————————————————————————————————————

function parseJob(job) {
  const b2bSalary = getB2BSalary(job);
  const secondaryInfo = getSecondarySalaryInfo(job);

  const locations = job.locations ?? [];
  const city = locations.length > 0 ? locations[0] : null;
  const locationStr = locations.length > 0 ? locations.join(", ") : "Remote";

  const isRemote = job.isRemote === true;
  const isHybrid = job.isHybrid === true;

  // Separate NiceToHave skills from required skills
  const requiredSkills = [];
  const niceToHaveSkills = [];
  for (const s of job.skills ?? []) {
    const name = (s.name ?? "").trim();
    if (!name) continue;
    if (s.level === "NiceToHave") {
      niceToHaveSkills.push(name);
    } else {
      requiredSkills.push(name);
    }
  }

  const category = [job.category ?? "", job.subCategory ?? ""]
    .filter(Boolean)
    .join(" / ");

  // Clean HTML from description for better text matching/LLM analysis
  const cleanDescription = stripHtml(job.description ?? "");

  return {
    // ─── Core identity ────────────────────────────────────────────
    external_id: `solidjobs_${job.jobOfferKey}`,
    platform: "solid.jobs",
    title: job.title ?? "Unknown",
    company: job.company ?? "Unknown",

    // ─── URLs ─────────────────────────────────────────────────────
    url: job.url ?? `https://solid.jobs/o/${job.jobOfferKey}`,
    company_logo_url: job.companyLogoUrl ?? null,

    // ─── Primary salary (always B2B) ──────────────────────────────
    salary_min: b2bSalary?.from ?? null,
    salary_max: b2bSalary?.to ?? null,
    currency: b2bSalary?.currency ?? "PLN",
    contract_type: "B2B",

    // ─── Location ─────────────────────────────────────────────────
    location: locationStr,
    city,
    remote: isRemote,
    hybrid: isHybrid,

    // ─── Skills & description ─────────────────────────────────────
    skills: requiredSkills,
    nice_to_have_skills: niceToHaveSkills,
    description: cleanDescription,
    category,
    experience_level: job.experienceLevel ?? "",

    // ─── Work info ────────────────────────────────────────────────
    working_time: (job.contractTime === "part_time") ? "part_time" : "full_time",
    division: job.division ?? "",

    // ─── Secondary salary (alternative contract type) ────────────
    secondary_salary_min: secondaryInfo.salary_min,
    secondary_salary_max: secondaryInfo.salary_max,
    secondary_currency: secondaryInfo.currency,
    secondary_contract_type: secondaryInfo.contract_type,

    // ─── Benefits & languages ─────────────────────────────────────
    benefits: JSON.stringify(job.benefits ?? []),
    languages: JSON.stringify(
      (job.languages ?? []).map((l) => ({ name: l.name, level: l.level }))
    ),

    // ─── Validity & timestamps ────────────────────────────────────
    valid_from: job.validFrom ?? null,
    valid_to: job.validTo ?? null,
    published_at: job.validFrom ?? null,
    updated_at: job.updatedAt ?? null,
    discovered_at: new Date().toISOString(),

    // ─── Raw data refs ─────────────────────────────────────────
    _raw: job._raw ?? [],
  };
}

// ——————————————————————————————————————————————————————————————————————————
//  Main
// ——————————————————————————————————————————————————————————————————————————

async function main() {
  log.info(`Starting (${TAGS.length} search tags, max ${MAX_PAGES} pages)`);

  const allJobs = [];

  for (let pageIdx = 0; pageIdx < MAX_PAGES; pageIdx++) {
    const { jobs, done } = await fetchPage(pageIdx);
    if (jobs.length > 0) allJobs.push(...jobs);
    if (done) break;
  }

  log.info(`Fetched ${allJobs.length} total offers`);

  // Filter: B2B + tag match
  const b2b = allJobs.filter((j) => getB2BSalary(j) !== null);
  log.info(`  → ${b2b.length} with B2B salary`);

  const matches = b2b.filter(isMatch).map(parseJob);
  log.info(`  → ${matches.length} tag-matched offers`);

  // Deduplicate + sort + write
  const jobs = sortBySalary(deduplicateByKey(matches, (j) => j.external_id));
  const deduped = matches.length - jobs.length;
  if (deduped > 0) log.info(`  → removed ${deduped} duplicates`);

  writeOutput("solidjobs", jobs);
  log.info(`Wrote ${jobs.length} jobs`);

  printTopJobs("[solidjobs]", jobs);

  return { platform: "solid.jobs", count: jobs.length, jobs };
}

if (require.main === module) {
  main().catch((err) => {
    console.error("[solidjobs] Fatal:", err);
    process.exit(1);
  });
}
module.exports = {
  metadata: {
    id: "solidjobs",
    name: "Solid.jobs",
    capabilities: ["api"],
    needsBrowser: false,
    platform: "solid.jobs",
    configFields: {
      max_pages: {
        type: "number",
        label: "Max Pages",
        description: "Maximum number of pagination pages to scrape",
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