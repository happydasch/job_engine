#!/usr/bin/env node
/**
 * Shared Output Writer — writeOutput(), printTopJobs(), printSummary().
 *
 * Consolidates the ~24 lines of fs.mkdirSync + JSON.stringify + sort +
 * top-N summary printing that is duplicated in every scraper file.
 *
 * Usage:
 *   const { writeOutput, printTopJobs } = require("./core/output");
 *   const result = writeOutput("justjoin_it", jobs);
 *   printTopJobs("[JustJoin.it]", jobs);
 */

const path = require("path");
const fs = require("fs");
const crypto = require("crypto");
const createLogger = require("./logger");
const { validateJobOffer } = require("./scraper-interface");
const { normalizeSkills } = require("./skills");

const log = createLogger("output");

const DATA_DIR = process.env.DATA_DIR || path.join(__dirname, "..", "..", "..", "data");
const OUTPUT_DIR = process.env.SCRAPER_OUTPUT_DIR || path.join(DATA_DIR, "scraper-output");

/**
 * Write jobs to disk sorted by salary descending.
 * Normalizes currencies before sorting — sorts highest-value-first approximately.
 *
 * @param {string} name — scraper id, e.g. "justjoin_it"
 * @param {object[]} jobs — job objects with salary_max
 * @param {object} [opts]
 * @param {string} [opts.outputDir] — override output directory
 * @returns {string} — the output file path
 */
function writeOutput(name, jobs, opts = {}) {
  const dir = opts.outputDir || OUTPUT_DIR;
  const file = path.join(dir, `${name}.json`);

  // Drop jobs missing required fields (schema drift / bad parse). Downstream
  // (Python save_jobs_sync) silently skips rows without external_id anyway, so
  // it's better to catch it here with a visible count than to write junk.
  const valid = jobs.filter((j) => validateJobOffer(j, name, { advisory: false }));
  const dropped = jobs.length - valid.length;
  if (dropped > 0) log.warn(`${name}: dropped ${dropped} invalid job(s) missing required fields`);

  // Normalize `requirements` → `description`: some scrapers populate the former,
  // but the canonical field name is `description`. Save_jobs_sync maps it already,
  // but normalizing here keeps the output JSON consistent.
  for (const job of valid) {
    if (job.requirements !== undefined && (job.description === undefined || job.description === "")) {
      job.description = job.requirements;
    }
    delete job.requirements;
  }

  // Normalize enum-like string fields: trim whitespace only (preserve original
  // casing). Fields: experience_level, contract_type.
  // Category and location are just trimmed as well.
  const STRING_FIELDS = ['experience_level', 'contract_type'];
  for (const job of valid) {
    for (const field of STRING_FIELDS) {
      if (job[field] && typeof job[field] === 'string') {
        job[field] = job[field].trim();
      }
    }
    if (job.category && typeof job.category === 'string') {
      job.category = job.category.trim();
    }
    if (job.location && typeof job.location === 'string') {
      job.location = job.location.trim();
    }
  }
  // Normalize skills: clean punctuation and whitespace while preserving
  // original casing. Underscores are converted to spaces so regex terms like
  // `machine_learning` become `machine learning`.
  for (const job of valid) {
    if (job.skills && Array.isArray(job.skills) && job.skills.length > 0) {
      job.skills = normalizeSkills(job.skills);
    }
    if (job.nice_to_have_skills && Array.isArray(job.nice_to_have_skills) && job.nice_to_have_skills.length > 0) {
      job.nice_to_have_skills = normalizeSkills(job.nice_to_have_skills);
    }
  }

  // Currency multiplier for approximate cross-currency comparison
  // Values are rough estimates — good enough for display sorting.
  const CURRENCY_MULTIPLIERS = { USD: 1, EUR: 1.05, GBP: 1.27, PLN: 0.25, CHF: 1.1 };

  const sorted = [...valid].sort((a, b) => {
    const aMul = CURRENCY_MULTIPLIERS[a.currency] ?? 1;
    const bMul = CURRENCY_MULTIPLIERS[b.currency] ?? 1;
    return ((b.salary_max ?? 0) * bMul) - ((a.salary_max ?? 0) * aMul);
  });
  try {
    fs.mkdirSync(dir, { recursive: true });
    fs.writeFileSync(file, JSON.stringify(sorted, null, 2));
  } catch (err) {
    log.error(`Failed to write output for ${name}: ${err.message}`);
    return null;
  }
  return file;
}

/**
 * Print a formatted top-N summary of jobs to stdout.
 *
 * @param {string} prefix — e.g. "[JustJoin.it]"
 * @param {object[]} jobs — sorted job objects
 * @param {number} [n=15] — how many to show
 */
function printTopJobs(prefix, jobs, n = 15) {
  const top = jobs.slice(0, n);
  if (top.length === 0) return;

  const label = `${prefix} Top ${top.length} matched offers:`;
  console.log(`\n${label}`);

  for (const job of top) {
    const sal = job.salary_max
      ? `${(job.salary_min ?? 0).toLocaleString()} - ${job.salary_max.toLocaleString()} ${job.currency}`
      : "N/A";
    const stack = (job.skills ?? []).slice(0, 5).join(", ");
    const location = job.location ? ` | ${job.location}` : "";
    console.log(`  ${job.title} @ ${job.company} | ${sal}${location}${stack ? ` [${stack}]` : ""}`);
  }
}

/**
 * Print a short one-line count summary.
 */
function printCountSummary(prefix, count, total = null) {
  const totalPart = total !== null ? ` (from ${total} raw)` : "";
  console.log(`${prefix} → ${count} matching offers${totalPart}`);
}

/**
 * Save raw source data alongside structured output.
 * Writes to output/raw/<scraper>/<externalId>.<html|json>.
 *
 * @param {string} scraper - e.g. "solidjobs"
 * @param {string} externalId - Job's external_id (sanitized for filesystem)
 * @param {string|object} data - Raw HTML or API response
 * @param {'html'|'json'} type - Content type
 * @param {object} [opts]
 * @param {string} [opts.outputDir] - Override output directory (default: SCRAPER_OUTPUT_DIR)
 * @returns {string|null} - Relative path from output/ (e.g. "raw/solidjobs/abc123.json"), or null on failure
 */
function saveRawData(scraper, externalId, data, type, opts = {}) {
  const dir = opts.outputDir || OUTPUT_DIR;
  // Sanitize externalId for filesystem safety (allow alphanumeric, hyphens, underscores, dots)
  const safeId = String(externalId).replace(/[^a-zA-Z0-9_.-]/g, "_").slice(0, 120);
  const ext = type === "json" ? "json" : "html";
  const rawDir = path.join(dir, "raw", scraper);
  const file = path.join(rawDir, `${safeId}.${ext}`);
  try {
    fs.mkdirSync(rawDir, { recursive: true });
    const content = type === "json" && typeof data === "object" ? JSON.stringify(data, null, 2) : String(data);
    fs.writeFileSync(file, content, "utf-8");
    // Return relative path from output/ directory
    return path.relative(dir, file);
  } catch (err) {
    log.warn(`Failed to save raw data for ${scraper}/${safeId}: ${err.message}`);
    return null;
  }
}

/**
 * Remove raw data files older than N scraper runs.
 * Reads run snapshots from output/runs/ to determine the last N runs, then
 * keeps only raw data directories for scrapers that had jobs in those runs.
 * Directories with no raw data at all are left untouched.
 *
 * @param {number} [keepRuns=3] - Number of recent runs to retain raw data for
 * @param {object} [opts]
 * @param {string} [opts.rawDir] - Override raw data directory (default: outputDir/raw)
 * @param {string} [opts.outputDir] - Override output directory
 */
function cleanRawData(keepRuns = 3, opts = {}) {
  const dir = opts.outputDir || OUTPUT_DIR;
  const rawBase = opts.rawDir || path.join(dir, "raw");
  const runsDir = path.join(dir, "runs");

  // Gather recent run snapshots
  let recentScrapers = new Set();
  try {
    if (fs.existsSync(runsDir)) {
      const snapshots = fs.readdirSync(runsDir)
        .filter((f) => f.endsWith(".json"))
        .sort()
        .reverse();
      const recent = snapshots.slice(0, keepRuns);
      for (const snap of recent) {
        const data = JSON.parse(fs.readFileSync(path.join(runsDir, snap), "utf-8"));
        // "per_platform" is the legacy key in snapshots from older runs.
        const perScraper = data.per_scraper || data.per_platform;
        if (perScraper) {
          for (const p of Object.keys(perScraper)) {
            recentScrapers.add(p);
          }
        }
      }
    }
  } catch (err) {
    log.warn(`Failed to read run snapshots for cleanup: ${err.message}`);
    return;
  }

  // Remove raw data directories for scrapers NOT in recent runs
  if (!fs.existsSync(rawBase)) return;
  try {
    const scrapers = fs.readdirSync(rawBase, { withFileTypes: true });
    let removed = 0;
    for (const entry of scrapers) {
      if (!entry.isDirectory()) continue;
      if (!recentScrapers.has(entry.name)) {
        const scraperDir = path.join(rawBase, entry.name);
        fs.rmSync(scraperDir, { recursive: true, force: true });
        removed++;
        log.info(`Cleaned raw data for scraper: ${entry.name} (not in recent ${keepRuns} runs)`);
      }
    }
    if (removed > 0) {
      log.info(`Cleaned raw data for ${removed} scraper(s) not in recent ${keepRuns} runs`);
    }
  } catch (err) {
    log.warn(`Failed to clean raw data: ${err.message}`);
  }
}

module.exports = { writeOutput, printTopJobs, printCountSummary, saveRawData, cleanRawData };