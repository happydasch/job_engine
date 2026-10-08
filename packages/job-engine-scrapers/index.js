#!/usr/bin/env node
/**
 * Scraper Discovery Barrel — index for the scrapers module.
 *
 * When this module is required (e.g. `require('./scrapers')`), it:
 * 1. Loads the ScraperRegistry singleton
 * 2. Discovers scrapers from:
 *    - Active packages in `data/active-scrapers/<id>/` (installed via the scraper store)
 *    - Installed npm packages in `node_modules/@job-engine-scrapers/scraper-*` (workspace symlinks)
 * 3. Each scraper self-registers via its `register()` function
 * 4. Logs registration summary
 *
 * ## Scraper Active Package Format
 * Each active scraper lives in `data/active-scrapers/<id>/` with:
 *   - `package.json`  — `@job-engine-scrapers/scraper-<id>` manifest
 *   - `index.js`      — re-exports from the source scraper in `scrapers/scrapers/<id>/`
 *   - `README.md`     — brief description
 *
 * Source packages in `scrapers/scrapers/<id>/` are NEVER discovered directly —
 * only active scrapers (those the user has installed via the store) are registered.
 *
 * @module scrapers/index
 */

const fs = require("fs");
const path = require("path");
const registry = require("./core/registry");

const ACTIVE_SCRAPERS_DIR = path.resolve(__dirname, "..", "..", "data", "active-scrapers");
const PACKAGE_SCOPE_DIR = path.resolve(__dirname, "node_modules", "@job-engine-scrapers");
const SOURCE_SCRAPERS_DIR = path.resolve(__dirname, "scrapers");

// ── Helpers ──────────────────────────────────────────────────────────────────

/**
 * Log to stderr so stdout stays clean for data output (e.g. dump-metadata.js).
 */
function log(msg) {
  process.stderr.write(`[scrapers] ${msg}\n`);
}

/**
 * Given a scraper ID, check if it's in the active-scrapers directory.
 *
 * @param {string} id
 * @returns {boolean}
 */
function isActive(id) {
  const activeDir = path.join(ACTIVE_SCRAPERS_DIR, id);
  return fs.existsSync(path.join(activeDir, "package.json")) || fs.existsSync(path.join(activeDir, "index.js"));
}

// ── Active Scraper Discovery ─────────────────────────────────────────────────

/**
 * Discover scrapers from data/active-scrapers/<id>/.
 * This is the primary discovery method — scrapers must be explicitly
 * "installed" via the scraper store to appear here.
 *
 * @param {import('./core/registry')} [reg]
 * @returns {number} Number of successfully registered scrapers
 */
function discoverActiveScrapers(reg) {
  reg = reg || registry;
  let registered = 0;

  let entries;
  try {
    if (!fs.existsSync(ACTIVE_SCRAPERS_DIR)) return 0;
    entries = fs.readdirSync(ACTIVE_SCRAPERS_DIR, { withFileTypes: true });
  } catch (err) {
    console.warn(`[scrapers] Cannot read active-scrapers directory: ${err.message}`);
    return 0;
  }

  for (const entry of entries) {
    if (!entry.isDirectory()) continue;
    if (entry.name === ".gitkeep") continue;

    const pkgDir = path.join(ACTIVE_SCRAPERS_DIR, entry.name);
    const indexFile = path.join(pkgDir, "index.js");
    const pkgJsonFile = path.join(pkgDir, "package.json");

    if (!fs.existsSync(indexFile) && !fs.existsSync(pkgJsonFile)) continue;

    try {
      const mod = require(indexFile);
      if (mod && typeof mod.register === "function") {
        mod.register(reg);
        const id = mod.metadata ? mod.metadata.id : entry.name;
        log(`Registered (active): ${id}`);
        registered++;
      }
    } catch (err) {
      console.warn(`[scrapers] Error loading active scraper ${entry.name}: ${err.message}`);
    }
  }

  return registered;
}

// ── Package Discovery (npm workspace symlinks) ─────────────────────────────────

/**
 * Discover installed npm packages under @job-engine-scrapers/scraper-*.
 * These are workspace symlinks to data/active-scrapers/<id>/.
 *
 * @param {import('./core/registry')} [reg]
 * @returns {number} Number of successfully registered scrapers
 */
function discoverPackages(reg) {
  reg = reg || registry;
  let registered = 0;

  try {
    if (!fs.existsSync(PACKAGE_SCOPE_DIR)) return 0;

    const entries = fs.readdirSync(PACKAGE_SCOPE_DIR, { withFileTypes: true });
    for (const entry of entries) {
      if (!entry.isDirectory()) continue;
      if (!entry.name.startsWith("scraper-")) continue;

      const pkgDir = path.join(PACKAGE_SCOPE_DIR, entry.name);
      const pkgJsonPath = path.join(pkgDir, "package.json");

      if (!fs.existsSync(pkgJsonPath)) continue;

      // Skip if this scraper is already registered via active-scrapers discovery
      const pkgId = entry.name.replace("scraper-", "");
      if (registry.get(pkgId)) continue;

      try {
        const mod = require(pkgDir);
        if (mod && typeof mod.register === "function") {
          mod.register(reg);
          const id = mod.metadata ? mod.metadata.id : pkgId;
          log(`Registered package: ${id} (@job-engine-scrapers/${entry.name})`);
          registered++;
        }
      } catch (err) {
        console.warn(`[scrapers] Error loading package ${entry.name}: ${err.message}`);
      }
    }
  } catch (err) {
    console.warn(`[scrapers] Error scanning package scope: ${err.message}`);
  }

  return registered;
}

/**
 * Discover all scrapers: first from data/active-scrapers/ (primary),
 * then from npm workspace packages (backward compat for non-active packages).
 *
 * @param {import('./core/registry')} [reg]
 * @returns {number} Number of successfully registered scrapers
 */
function discover(reg) {
  reg = reg || registry;

  const activeCount = discoverActiveScrapers(reg);
  const pkgCount = discoverPackages(reg);

  return activeCount + pkgCount;
}

// ── Auto-register on require() ───────────────────────────────────────────────

const count = discover(registry);
log(`Discovery complete: ${count} scrapers registered (total: ${registry.size})`);

// ── Exports ──────────────────────────────────────────────────────────────────

module.exports = {
  registry,
  discover,
  isActive,
  ACTIVE_SCRAPERS_DIR,
};