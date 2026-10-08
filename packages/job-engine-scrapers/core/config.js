/**
 * Scraper Config & Profile Tags — shared config for all scrapers.
 *
 * Concerns separated:
 *   - scraper_config.yaml      → scraper enabled states, max_offer_duration_days
 *   - my_profile.yaml          → search tags (skills, boosted_keywords)
 *
 * Provides:
 *   - getTags()                          → ['python', 'fastapi', …]  (from profile)
 *   - getScraper(name)                  → { enabled, max_pages }
 *   - getActiveScrapers()               → [{ id, config }, …]
 *   - getRegisteredActiveScrapers()     → [{ id, config }, …]
 *
 * CLI modes:
 *   node scrapers/config.js --preview   → print config summary
 *   node scrapers/config.js             → print summary
 */

const fs = require("fs");
const path = require("path");
const yaml = require("js-yaml");

const CONFIG_FILE = process.env.SCRAPER_CONFIG_PATH
  ? path.resolve(process.env.SCRAPER_CONFIG_PATH)
  : path.resolve(__dirname, "..", "..", "..", "data", "scraper_config.yaml");
const PROFILE_FILE = path.resolve(__dirname, "..", "..", "..", "data", "my_profile.yaml");

// ─── YAML parsing (js-yaml, shared with the Python side) ──────────────────

function parseYAML(text) {
  const parsed = yaml.load(text);
  return parsed && typeof parsed === "object" ? parsed : {};
}

// ─── Scraper config (scrapers, max_age) — from scraper_config.yaml ─────────

let _configCache = null;

function loadConfig() {
  if (_configCache) return _configCache;

  const defaults = { scrapers: {}, max_offer_duration_days: 30 };

  if (!fs.existsSync(CONFIG_FILE)) {
    _configCache = defaults;
    return _configCache;
  }

  const raw = fs.readFileSync(CONFIG_FILE, "utf-8");
  const parsed = parseYAML(raw);

  // "platforms" is the legacy YAML key for scrapers in old config files.
  const scrapersBlock = parsed.scrapers != null ? parsed.scrapers : parsed.platforms;

  _configCache = {
    scrapers: (typeof scrapersBlock === "object" && scrapersBlock !== null)
      ? scrapersBlock
      : {},
    max_offer_duration_days: typeof parsed.max_offer_duration_days === "number"
      ? parsed.max_offer_duration_days
      : 30,
  };
  return _configCache;
}

// ─── Tags from my_profile.yaml ─────────────────────────────────────────────

let _tagsCache = null;

function loadTags() {
  if (_tagsCache) return _tagsCache;

  if (!fs.existsSync(PROFILE_FILE)) {
    _tagsCache = [];
    return _tagsCache;
  }

  const raw = fs.readFileSync(PROFILE_FILE, "utf-8");
  const parsed = parseYAML(raw);

  // Collect all skills from all categories
  const allTags = new Set();

  function collectStrings(obj) {
    if (!obj || typeof obj !== "object") return;
    for (const val of Object.values(obj)) {
      if (Array.isArray(val)) {
        for (const item of val) {
          if (typeof item === "string") allTags.add(item.trim().toLowerCase());
        }
      } else if (typeof val === "object") {
        collectStrings(val);
      }
    }
  }

  // Collect from skills subtree
  if (parsed.skills && typeof parsed.skills === "object") {
    collectStrings(parsed.skills);
  }

  // Add boosted keywords
  const boosted = parsed.boosted_keywords;
  if (Array.isArray(boosted)) {
    for (const kw of boosted) {
      if (typeof kw === "string") allTags.add(kw.trim().toLowerCase());
    }
  }

  _tagsCache = [...allTags].sort();
  return _tagsCache;
}

let _profileCache = null;

function loadProfile() {
  if (_profileCache) return _profileCache;
  if (!fs.existsSync(PROFILE_FILE)) {
    _profileCache = {};
    return _profileCache;
  }
  _profileCache = parseYAML(fs.readFileSync(PROFILE_FILE, "utf-8"));
  return _profileCache;
}

function invalidateCache() {
  _configCache = null;
  _tagsCache = null;
  _profileCache = null;
}

// ─── Public API ────────────────────────────────────────────────────────────

var api = {};

api.getTags = function getTags() {
  return loadTags();
};

api.getSearchTerms = function getSearchTerms() {
  const profile = loadProfile();
  const boosted = profile.boosted_keywords;
  if (Array.isArray(boosted) && boosted.length > 0) {
    return [...new Set(boosted.filter((k) => typeof k === "string").map((k) => k.trim().toLowerCase()))];
  }
  return api.getTags();
};

api.getRemoteOnly = function getRemoteOnly() {
  const profile = loadProfile();
  return profile.preferences && profile.preferences.remote_only === true;
};

api.getPreferredLocations = function getPreferredLocations() {
  const profile = loadProfile();
  const locs = profile.preferred_locations;
  return Array.isArray(locs) ? locs.filter((l) => typeof l === "string" && l.trim()) : [];
};

api.getScraper = function getScraper(id) {
  const cfg = loadConfig();
  const scrapers = cfg.scrapers;
  const block = scrapers[id];
  if (!block) return null;
  // Return ALL fields from the YAML block so scrapers can access
  // custom per-scraper settings (max_pages, timeout_seconds,
  // request_delay_ms, concurrency, etc.) without config.js needing
  // to know about each field individually.
  const result = { ...block };
  result.enabled = block.enabled !== false;
  if (result.max_pages == null) result.max_pages = 1;
  return result;
};

api.getActiveScrapers = function getActiveScrapers() {
  const cfg = loadConfig();
  return Object.entries(cfg.scrapers)
    .filter(function(_ref) {
      var p = _ref[1];
      return p.enabled !== false;
    })
    .map(function(_ref2) {
      var id = _ref2[0];
      var p = _ref2[1];
      // Return ALL fields from the YAML block, not just enabled + max_pages.
      // This allows custom per-scraper settings (timeout, concurrency, delay, etc.)
      // to flow through to the runner and individual scraper modules.
      const result = { ...p };
      result.id = id;
      result.enabled = true;
      if (result.max_pages == null) result.max_pages = 1;
      return result;
    });
};

// ─── Registry integration ────────────────────────────────────────────────────

api.getRegisteredActiveScrapers = function getRegisteredActiveScrapers() {
  const active = api.getActiveScrapers();
  try {
    const registry = require("./registry");
    const registeredIds = new Set(registry.getAll().map(function(m) { return m.metadata.id; }));
    return active.filter(function(p) { return registeredIds.has(p.id); });
  } catch (_) {
    console.warn(`[config] Failed to load registry for active filter: ${_?.message || "unknown error"}`);
    return active;
  }
};

// Deprecated aliases — "platform" was the old name for scraper. Kept so
// already-installed scraper packages built against the old API keep working.
api.getPlatform = api.getScraper;
api.getActivePlatforms = api.getActiveScrapers;
api.getRegisteredActivePlatforms = api.getRegisteredActiveScrapers;

// ─── CLI modes ─────────────────────────────────────────────────────────────

if (require.main === module) {
  const args = process.argv.slice(2);

  if (args.includes("--preview")) {
    console.log("\n╔══════════════════════════════════════════════════════════╗");
    console.log("║  SCRAPER CONFIG PREVIEW                                ║");
    console.log("╚══════════════════════════════════════════════════════════╝\n");

    const tags = api.getTags();
    console.log("Tags (from my_profile.yaml): " + tags.length);
    console.log("  " + tags.slice(0, 10).join(", ") + (tags.length > 10 ? ", …" : "") + "\n");

    const active = api.getActiveScrapers();
    console.log("Scrapers (from scraper_config.yaml): " + active.length + " active");
    for (const p of active) {
      console.log("  " + p.id);
    }
    console.log();
    console.log("Note: URL-based search templates have been removed. Each scraper is responsible for how it fetches data (API, Playwright, etc.).");
    return;
  }

  // Default: print summary
  const tags = api.getTags();
  const cfg = loadConfig();
  console.log("[config] " + tags.length + " tags (from my_profile.yaml), " + Object.keys(cfg.scrapers).length + " scrapers configured (from scraper_config.yaml)");
}

// ─── Max offer duration config ────────────────────────────────────────────

const DEFAULT_MAX_OFFER_DURATION_DAYS = 30;

api.getMaxOfferDurationDays = function getMaxOfferDurationDays() {
  try {
    const cfg = loadConfig();
    return cfg.max_offer_duration_days != null ? cfg.max_offer_duration_days : DEFAULT_MAX_OFFER_DURATION_DAYS;
  } catch (_) {
    console.warn(`[config] Failed to load max_offer_duration_days, using default (${DEFAULT_MAX_OFFER_DURATION_DAYS}): ${_?.message || "unknown error"}`);
    return DEFAULT_MAX_OFFER_DURATION_DAYS;
  }
};

// ─── URL skip list ────────────────────────────────────────────────────────

const SKIP_LIST_FILE = process.env.SCRAPER_SKIP_LIST_PATH
  ? path.resolve(process.env.SCRAPER_SKIP_LIST_PATH)
  : path.resolve(__dirname, "..", "..", "..", "urls_to_skip.txt");

let _skipListCache = null;

api.getUrlsToSkip = function getUrlsToSkip() {
  if (_skipListCache) return _skipListCache;

  try {
    if (fs.existsSync(SKIP_LIST_FILE)) {
      const content = fs.readFileSync(SKIP_LIST_FILE, "utf-8");
      const urls = content
        .split("\n")
        .map(function(l) { return l.trim(); })
        .filter(function(l) { return l && !l.startsWith("#"); });
      _skipListCache = new Set(urls);
      if (urls.length > 0) {
        console.log("[config] Loaded " + urls.length + " URLs to skip from " + SKIP_LIST_FILE);
      }
    } else {
      _skipListCache = new Set();
    }
  } catch (err) {
    console.warn("[config] Failed to load skip list: " + err.message);
    _skipListCache = new Set();
  }

  return _skipListCache;
};

module.exports = api;
