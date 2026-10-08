#!/usr/bin/env node
/**
 * Job Scraper Orchestrator
 *
 * Runs all active scrapers (defined in scraper_config.yaml via config.js)
 * as subprocesses, collects results, collects per-scraper metrics,
 * and prints a unified summary. Handles Playwright availability
 * gracefully with timeouts.
 *
 * Usage:
 *   node scrapers/run.js
 */

const fs = require("fs");
const path = require("path");
const { spawn } = require("child_process");

const DATA_DIR = process.env.DATA_DIR || path.join(__dirname, "..", "..", "data");
const OUTPUT_DIR = path.join(DATA_DIR, "scraper-output");
// 48 tags x up to ~13s of human-mimic delay/scroll per tag can legitimately take ~10min
// for a scraper that isn't blocked but also isn't fast (e.g. solidjobs) — 120s killed it mid-run.
const SCRAPER_TIMEOUT_MS = parseInt(process.env.SCRAPER_TIMEOUT_MS || "600000", 10);

// Concurrency caps. Browser scrapers each spawn a full Playwright subprocess
// (heavy — RAM + CPU), so they run fewer-at-a-time than the lightweight,
// I/O-bound fetch/api scrapers that run in-process.
const INPROC_CONCURRENCY = parseInt(process.env.SCRAPER_INPROC_CONCURRENCY || "8", 10);
const BROWSER_CONCURRENCY = parseInt(process.env.SCRAPER_BROWSER_CONCURRENCY || "3", 10);

// ——————————————————————————————————————————————————————————————————————————
//  Config-driven scraper registry
// ——————————————————————————————————————————————————————————————————————————

require("./core/proxy.js");
const log = require("./core/logger")("run");
const config = require("./core/config");

// Load the ScraperRegistry — this triggers auto-discovery of scrapers from
// data/active-scrapers/<id>/ (installed via install-scraper.js or the store).
// Scrapers in the source directory (scrapers/<id>/) are NOT auto-discovered
// until they are installed (which creates the active wrapper).
const { registry } = require("./index");
const { cleanRawData } = require("./core/output");

// Active scrapers — only those both registered AND enabled in config
function resolveScraperEntry(id) {
  // Primary: data/active-scrapers/<id>/index.js (installed via store)
  const activeIndex = path.join(__dirname, "..", "..", "data", "active-scrapers", id, "index.js");
  if (fs.existsSync(activeIndex)) return activeIndex;
  // Fallback to source: scrapers/scrapers/<id>/index.js
  const pkgIndex = path.join(__dirname, "scrapers", id, "index.js");
  if (fs.existsSync(pkgIndex)) return pkgIndex;
  // Fall back to old flat file: scrapers/scrapers/<id>.js
  return path.join(__dirname, `scrapers/${id}.js`);
}

/**
 * Resolve the effective timeout in ms for a given scraper.
 * Uses the per-scraper `timeout_seconds` config field if set (> 0),
 * otherwise falls back to the global SCRAPER_TIMEOUT_MS.
 */
function getScraperTimeoutMs(scraper) {
  const perScraperSec = scraper.cfg?.timeout_seconds;
  if (perScraperSec && perScraperSec > 0) {
    return perScraperSec * 1000;
  }
  return SCRAPER_TIMEOUT_MS;
}

const SCRAPERS = config.getRegisteredActiveScrapers().map((p) => ({
  id: p.id,
  file: resolveScraperEntry(p.id),
  needsBrowser: registry.get(p.id)?.metadata?.needsBrowser || false,
  // Per-scraper config fields from scraper_config.yaml (e.g. timeout_seconds)
  // are available via config.getScraper(p.id) in the runner functions below.
  cfg: config.getScraper(p.id),
}));

const TAGS = config.getTags();

log.info(`Scrapers: ${SCRAPERS.length} active (total registered: ${registry.size})`, { tags: TAGS.length });

// ——————————————————————————————————————————————————————————————————————————
//  Helpers
// ——————————————————————————————————————————————————————————————————————————

// Structured event marker consumed by the Python dashboard (scraper_runner.py).
// Emitting machine-readable events decouples the dashboard from human log text.
const EVENT_MARKER = "##SCRAPER_EVENT##";

function emitEvent(obj) {
  console.log(`${EVENT_MARKER} ${JSON.stringify(obj)}`);
}

function getOutputPath(name) {
  return path.join(OUTPUT_DIR, `${name}.json`);
}

/**
 * Read a subprocess scraper's output file, written during this run.
 *
 * No fallbacks: a missing file, a file that predates `notBefore` (stale
 * leftover from a previous run), or unparseable JSON all throw — the caller
 * records the error on the scraper result instead of silently reporting
 * 0 (or worse, resurrected stale) jobs.
 */
function loadResults(name, notBefore) {
  const file = getOutputPath(name);
  if (!fs.existsSync(file)) {
    throw new Error(`Output file not written: ${file}`);
  }
  const mtime = fs.statSync(file).mtimeMs;
  if (notBefore && mtime < notBefore) {
    throw new Error(`Output file is stale (written before this run): ${file}`);
  }
  const raw = fs.readFileSync(file, "utf-8");
  try {
    return JSON.parse(raw);
  } catch (err) {
    throw new Error(`Output file is not valid JSON (${file}): ${err.message}`);
  }
}

function isPlaywrightAvailable() {
  try {
    require.resolve("playwright");
    return true;
  } catch { /* Optional dependency, ignore if unavailable */
    return false;
  }
}

function printSeparator(char = "=") {
  console.log(char.repeat(80));
}

// ——————————————————————————————————————————————————————————————————————————
//  Subprocess runner (preferred over require() to avoid caching issues)
// ——————————————————————————————————————————————————————————————————————————

function runSubprocess(scraper) {
  return new Promise((resolve) => {
    let resolved = false;
    emitEvent({ type: "scraper_start", id: scraper.id });

    const scraperPath = scraper.file;
    if (!fs.existsSync(scraperPath)) {
      // A registered + enabled scraper whose entry file is missing is a real
      // failure (broken install), not a skip.
      const error = `Scraper entry file not found: ${scraperPath}`;
      log.error(error, { scraper: scraper.id });
      emitEvent({ type: "scraper_done", id: scraper.id, jobs: 0, duration: 0, error, skipped: false });
      return resolve({ id: scraper.id, jobs: [], duration: 0, error, skipped: false });
    }

    // Skip browser scrapers if Playwright is not installed. Report 0 jobs and a
    // skipped flag — do NOT resurrect stale results from a previous run and
    // count them as if this run produced them.
    if (scraper.needsBrowser && !isPlaywrightAvailable()) {
      log.info(`Skipped — Playwright not available`, { scraper: scraper.id });
      emitEvent({ type: "scraper_done", id: scraper.id, jobs: 0, duration: 0, error: null, skipped: true });
      return resolve({ id: scraper.id, jobs: [], duration: 0, skipped: true });
    }

    const start = Date.now();
    const child = spawn("node", [scraperPath], {
      cwd: __dirname,
      stdio: ["ignore", "pipe", "pipe"],
      env: { ...process.env, SCRAPER_OUTPUT_DIR: OUTPUT_DIR },
    });

    // Forward child output live (line-buffered) instead of buffering until the
    // process exits — the dashboard tails our stdout, so this gives real-time
    // progress rather than a silent gap for long-running scrapers.
    child.stdout.on("data", (chunk) => process.stdout.write(chunk));
    child.stderr.on("data", (chunk) => process.stderr.write(chunk));

    const timeoutMs = getScraperTimeoutMs(scraper);
    const timer = setTimeout(() => {
      log.warn(`Timeout — killing ${scraper.id} after ${timeoutMs}ms`);
      // Emit scraper_done BEFORE killing so the event reaches stdout even if the
      // Python side kills our process at the same time (both use the same timeout
      // value). Setting resolved=true prevents the close handler from double-emitting.
      if (!resolved) {
        resolved = true;
        const duration = (Date.now() - start) / 1000;
        emitEvent({ type: "scraper_done", id: scraper.id, jobs: 0, duration, error: "Timed out", skipped: false });
      }
      child.kill("SIGTERM");
      // Grace period then SIGKILL
      setTimeout(() => {
        if (!child.killed) {
          log.warn(`SIGKILL — ${scraper.id} did not respond to SIGTERM`);
          child.kill("SIGKILL");
        }
      }, 5000);
    }, timeoutMs);

    child.on("close", (code) => {
      if (resolved) return;
      resolved = true;
      clearTimeout(timer);
      const duration = (Date.now() - start) / 1000;

      // code can be null when killed by signal
      const exitOk = code === 0 || code === null;
      if (!exitOk) {
        log.warn(`Exited with code ${code}`, { scraper: scraper.id, duration });
      }

      let jobs = [];
      let error = !exitOk ? `Exit code ${code}` : null;
      try {
        jobs = loadResults(scraper.id, start);
      } catch (err) {
        error = error || err.message;
        log.error(`Failed to load output`, { scraper: scraper.id, error: err.message });
      }
      if (!error) {
        log.info(`Completed`, { scraper: scraper.id, jobs: jobs.length, duration: `${duration.toFixed(1)}s` });
      }
      emitEvent({ type: "scraper_done", id: scraper.id, jobs: jobs.length, duration, error, skipped: false });
      resolve({ id: scraper.id, jobs, duration, error });
    });

    child.on("error", (err) => {
      if (resolved) return;
      resolved = true;
      clearTimeout(timer);
      log.error(`Spawn failed`, { scraper: scraper.id, error: err.message });
      emitEvent({ type: "scraper_done", id: scraper.id, jobs: 0, duration: 0, error: err.message, skipped: false });
      resolve({ id: scraper.id, jobs: [], duration: 0, error: err.message });
    });
  });
}

// ——————————————————————————————————————————————————————————————————————————
//  In-process runner (for fetch/api scrapers — no subprocess overhead)
// ——————————————————————————————————————————————————————————————————————————

/**
 * Race a promise against a timeout. The underlying work is NOT cancelled on
 * timeout (in-process has no SIGKILL equivalent) — we just stop waiting and
 * report a timeout error. Fetch/api scrapers settle quickly in practice, so a
 * lingering background promise is a rare, bounded cost. Browser scrapers, which
 * genuinely need hard-kill, stay in the subprocess path above.
 */
function withTimeout(promise, ms, id) {
  let timer;
  const timeout = new Promise((_, reject) => {
    timer = setTimeout(() => reject(new Error(`In-process scraper "${id}" timed out after ${ms}ms`)), ms);
  });
  return Promise.race([promise, timeout]).finally(() => clearTimeout(timer));
}

/**
 * Run a fetch/api scraper by calling its registered main() directly in this
 * process. Uses the returned { jobs } array as the source of truth — never
 * reads output/<id>.json — so a crash cannot resurrect a previous run's stale
 * results (the bug the old subprocess loadResults() path was prone to).
 */
async function runInProcess(scraper) {
  emitEvent({ type: "scraper_start", id: scraper.id });
  const start = Date.now();

  const mod = registry.get(scraper.id);
  if (!mod || typeof mod.main !== "function") {
    log.warn(`No registered main() for ${scraper.id}`);
    emitEvent({ type: "scraper_done", id: scraper.id, jobs: 0, duration: 0, error: "No main()", skipped: true });
    return { id: scraper.id, jobs: [], duration: 0, error: "No main()", skipped: true };
  }

  try {
    // Wrap in Promise.resolve().then() so a synchronous throw inside main()
    // (before its first await) is caught here rather than crashing run.js.
    const result = await withTimeout(
      Promise.resolve().then(() => mod.main()),
      getScraperTimeoutMs(scraper),
      scraper.id
    );
    const jobs = Array.isArray(result?.jobs) ? result.jobs : [];
    const duration = (Date.now() - start) / 1000;
    log.info(`Completed`, { scraper: scraper.id, jobs: jobs.length, duration: `${duration.toFixed(1)}s`, mode: "inproc" });
    emitEvent({ type: "scraper_done", id: scraper.id, jobs: jobs.length, duration, error: null, skipped: false });
    return { id: scraper.id, jobs, duration, error: null };
  } catch (err) {
    const duration = (Date.now() - start) / 1000;
    log.error(`In-process scraper failed`, { scraper: scraper.id, error: err.message });
    emitEvent({ type: "scraper_done", id: scraper.id, jobs: 0, duration, error: err.message, skipped: false });
    return { id: scraper.id, jobs: [], duration, error: err.message };
  }
}

// ——————————————————————————————————————————————————————————————————————————
//  Bounded-concurrency pool
// ——————————————————————————————————————————————————————————————————————————

/**
 * Run `worker(item)` over `items` with at most `concurrency` in flight.
 * Preserves input order in the returned results array. `worker` is expected to
 * never reject (runInProcess/runSubprocess both catch internally and resolve).
 */
async function runPool(items, worker, concurrency) {
  const results = new Array(items.length);
  let cursor = 0;
  async function runner() {
    while (cursor < items.length) {
      const i = cursor++;
      results[i] = await worker(items[i]);
    }
  }
  const n = Math.max(1, Math.min(concurrency, items.length));
  await Promise.all(Array.from({ length: n }, runner));
  return results;
}

// ——————————————————————————————————————————————————————————————————————————
//  Summary printer
// ——————————————————————————————————————————————————————————————————————————

function printSummary(allJobs, metrics) {
  printSeparator();
  console.log("  B2B JOB SEARCH — SUMMARY");
  console.log(`  ${new Date().toISOString()}`);
  console.log(`  Tags (${TAGS.length}): ${TAGS.slice(0, 12).join(", ")}${TAGS.length > 12 ? ", …" : ""}`);
  printSeparator();

  for (const [scraper, jobs] of Object.entries(allJobs)) {
    console.log(`\n  ${scraper.toUpperCase()} — ${jobs.length} matches`);

    for (const job of jobs.slice(0, 10)) {
      const sal = job.salary_max
        ? `${(job.salary_min ?? 0).toLocaleString()} - ${job.salary_max.toLocaleString()} ${job.currency}`
        : "N/A  ";
      const stack = (job.skills ?? []).slice(0, 5).join(", ");
      console.log(
        `  ${job.title.padEnd(50)} ${sal.padEnd(20)} ${job.company.padEnd(20)}`
      );
      console.log(`  ${`→ ${job.url}`.padEnd(60)} ${stack ? `[${stack}]` : ""}`);
    }
    if (jobs.length > 10) {
      console.log(`  … and ${jobs.length - 10} more`);
    }
  }

  // Cross-scraper totals
  const all = Object.values(allJobs).flat();
  printSeparator();
  console.log(`  TOTAL: ${all.length} matching B2B offers`);

  // Per-scraper metrics
  console.log(`\n  PER-SCRAPER METRICS:`);
  for (const m of metrics) {
    const status = m.error ? "ERR" : "OK";
    console.log(`     ${status}  ${m.id.padEnd(14)} ${m.jobs} jobs  ${m.duration.toFixed(1)}s  ${m.error || ""}`);
  }

  // Top 5 highest-paying
  const sorted = [...all].sort((a, b) => (b.salary_max ?? 0) - (a.salary_max ?? 0));
  console.log(`\n  TOP 5 HIGHEST-PAYING:`);
  for (const job of sorted.slice(0, 5)) {
    const sal = job.salary_max
      ? `${(job.salary_min ?? 0).toLocaleString()} - ${job.salary_max.toLocaleString()} ${job.currency}`
      : "N/A";
    const stack = (job.skills ?? []).slice(0, 4).join(", ");
    console.log(`     ${job.title} @ ${job.company} — ${sal}`);
    console.log(`     ${job.url}`);
    console.log(`     [${stack}]`);
  }
}

// ——————————————————————————————————————————————————————————————————————————
//  Main
// ——————————————————————————————————————————————————————————————————————————

async function main() {
  // Ensure output directory
  fs.mkdirSync(OUTPUT_DIR, { recursive: true });

  const allResults = {};
  const metrics = [];

  // Split by execution mode: browser scrapers run as killable subprocesses
  // (Playwright isolation), fetch/api scrapers run in-process (no VM spawn,
  // no file round-trip). Each group has its own concurrency cap.
  const browserScrapers = SCRAPERS.filter((s) => s.needsBrowser);
  const inprocScrapers = SCRAPERS.filter((s) => !s.needsBrowser);

  log.info(
    `Starting ${SCRAPERS.length} scrapers` +
      ` (${inprocScrapers.length} in-process ≤${INPROC_CONCURRENCY}, ${browserScrapers.length} browser-subprocess ≤${BROWSER_CONCURRENCY})`
  );

  const [inprocResults, browserResults] = await Promise.all([
    runPool(inprocScrapers, runInProcess, INPROC_CONCURRENCY),
    runPool(browserScrapers, runSubprocess, BROWSER_CONCURRENCY),
  ]);

  for (const result of [...inprocResults, ...browserResults]) {
    if (!result) continue;
    allResults[result.id] = result.jobs;
    metrics.push({ id: result.id, jobs: result.jobs.length, duration: result.duration, error: result.error });
  }

  // Write unified output — catch serialization errors so a single corrupt
  // job object doesn't crash the process without a trace.
  const unified = Object.values(allResults).flat();
  unified.sort((a, b) => (b.salary_max ?? 0) - (a.salary_max ?? 0));
  let allJsonError = null;
  try {
    fs.writeFileSync(
      path.join(OUTPUT_DIR, "_all.json"),
      JSON.stringify(unified, null, 2)
    );
  } catch (err) {
    allJsonError = err.message;
    log.error("Failed to write _all.json", { error: err.message });
  }

  // Write run snapshot for history tracking — best-effort, never fatal.
  try {
    const snapshotDir = path.join(OUTPUT_DIR, "runs");
    fs.mkdirSync(snapshotDir, { recursive: true });
    const runDate = new Date().toISOString().replace(/[:.]/g, "-").slice(0, 19);
    const snapshotFile = path.join(snapshotDir, `${runDate}.json`);
    fs.writeFileSync(
      snapshotFile,
      JSON.stringify(
        {
          run_at: new Date().toISOString(),
          tags: TAGS,
          scrapers: SCRAPERS.map(s => s.id),
          total_jobs: unified.length,
          per_scraper: Object.fromEntries(
            Object.entries(allResults).map(([id, jobs]) => [id, jobs.length])
          ),
          metrics: metrics.map(m => ({ id: m.id, jobs: m.jobs, duration_s: m.duration, error: m.error })),
          top_highest_paying: unified.slice(0, 10).map(j => ({
            title: j.title,
            company: j.company,
            salary_max: j.salary_max,
            currency: j.currency,
            url: j.url,
          })),
        },
        null,
        2
      )
    );
    log.info(`Snapshot saved to ${snapshotFile}`);
  } catch (err) {
    log.warn("Failed to write run snapshot", { error: err.message });
  }

  // If _all.json could not be written the run is effectively failed — let the
  // Python side see exit code 1 so it records a failure rather than seeding
  // a stale _all.json from a previous run.
  if (allJsonError) {
    log.error("Run failed — _all.json was not written");
    throw new Error(`Failed to write _all.json: ${allJsonError}`);
  }

  printSummary(allResults, metrics);

  // Clean up raw data from previous runs (keep recent 3)
  cleanRawData(3, { outputDir: OUTPUT_DIR });

  return { allResults, metrics };
}

if (require.main === module) {
  main().catch((err) => {
    log.error("Fatal", { error: err.message, stack: err.stack });
    process.exit(1);
  });
}

module.exports = { main, SCRAPERS };