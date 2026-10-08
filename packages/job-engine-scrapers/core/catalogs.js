#!/usr/bin/env node
/**
 * Scraper Catalog Configuration — read/write catalog definitions.
 *
 * Reads data/scraper_catalogs.yaml and provides a clean API for:
 *   - Loading all catalogs
 *   - Looking up a catalog by ID
 *   - Getting the default catalog (first enabled)
 *   - CRUD operations on catalogs
 *
 * Catalog types:
 *   - "npm":   npm registry with @scope filter
 *   - "local": local filesystem directory of scraper packages
 *   - "git":   git repository URL (installed via npm install git+<url>)
 *
 * @module @job-engine-scrapers/core/catalogs
 */

const fs = require("fs");
const path = require("path");
const yaml = require("js-yaml");

/**
 * @typedef {Object} CatalogDef
 * @property {string} id        - Unique catalog identifier
 * @property {string} name      - Display name
 * @property {"npm"|"local"|"git"} type - Catalog type
 * @property {string} [scope]   - npm scope (e.g. "@job-engine-scrapers"), for npm type
 * @property {string} [registry] - npm registry URL, for npm type
 * @property {string} [path]    - filesystem path, for local type
 * @property {string} [url]     - git URL, for git type
 * @property {string} [ref]     - git branch/tag, for git type
 * @property {boolean} enabled  - Whether this catalog is active
 */

// ── Paths ──────────────────────────────────────────────────────────────────

const CATALOGS_FILE = process.env.SCRAPER_CATALOGS_PATH
  ? path.resolve(process.env.SCRAPER_CATALOGS_PATH)
  : path.resolve(__dirname, "..", "..", "..", "data", "scraper_catalogs.yaml");

// ── Load / Save ─────────────────────────────────────────────────────────────

/**
 * Load all catalog definitions from scraper_catalogs.yaml.
 * Returns an empty array on error.
 *
 * @returns {CatalogDef[]}
 */
function loadCatalogs() {
  try {
    if (!fs.existsSync(CATALOGS_FILE)) {
      // Fall back to the config/ template if no data/ copy exists yet
      const template = path.resolve(__dirname, "..", "..", "..", "config", "scraper_catalogs.yaml");
      if (fs.existsSync(template)) {
        const dir = path.dirname(CATALOGS_FILE);
        if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });
        fs.copyFileSync(template, CATALOGS_FILE);
      } else {
        return [];
      }
    }
    const raw = fs.readFileSync(CATALOGS_FILE, "utf-8");
    const parsed = yaml.load(raw);
    if (!parsed || typeof parsed !== "object" || !Array.isArray(parsed.catalogs)) {
      return [];
    }
    return parsed.catalogs;
  } catch (err) {
    console.warn(`[catalogs] Failed to load catalog config: ${err.message}`);
    return [];
  }
}

/**
 * Save catalog definitions to scraper_catalogs.yaml.
 *
 * @param {CatalogDef[]} catalogs
 * @returns {boolean} true on success
 */
function saveCatalogs(catalogs) {
  try {
    const doc = { catalogs };
    // Use yaml.dump with formatting to preserve readability
    const output = yaml.dump(doc, {
      indent: 2,
      lineWidth: 120,
      noRefs: true,
      sortKeys: false,
    });
    fs.writeFileSync(CATALOGS_FILE, output, "utf-8");
    return true;
  } catch (err) {
    console.warn(`[catalogs] Failed to save catalog config: ${err.message}`);
    return false;
  }
}

// ── Lookup ──────────────────────────────────────────────────────────────────

/**
 * Get a catalog by ID.
 *
 * @param {string} id
 * @returns {CatalogDef|null}
 */
function getCatalog(id) {
  const catalogs = loadCatalogs();
  return catalogs.find((s) => s.id === id) || null;
}

/**
 * Get the first enabled catalog (the default).
 * Falls back to the first catalog overall if none are enabled.
 *
 * @returns {CatalogDef|null}
 */
function getDefaultCatalog() {
  const catalogs = loadCatalogs();
  const enabled = catalogs.filter((s) => s.enabled !== false);
  return enabled.length > 0 ? enabled[0] : catalogs.length > 0 ? catalogs[0] : null;
}

/**
 * Get all catalogs, or all enabled catalogs.
 *
 * @param {boolean} [enabledOnly=false] - If true, return only enabled catalogs
 * @returns {CatalogDef[]}
 */
function listCatalogs(enabledOnly) {
  const catalogs = loadCatalogs();
  if (enabledOnly) {
    return catalogs.filter((s) => s.enabled !== false);
  }
  return catalogs;
}

// ── CRUD ────────────────────────────────────────────────────────────────────

/**
 * Add a catalog definition.
 *
 * @param {CatalogDef} def
 * @returns {{ success: boolean, error?: string }}
 */
function addCatalog(def) {
  if (!def || !def.id || !def.type) {
    return { success: false, error: "Catalog must have 'id' and 'type' fields" };
  }

  const validTypes = ["npm", "local", "git"];
  if (!validTypes.includes(def.type)) {
    return { success: false, error: `Invalid catalog type '${def.type}'. Must be one of: ${validTypes.join(", ")}` };
  }

  const catalogs = loadCatalogs();
  if (catalogs.some((s) => s.id === def.id)) {
    return { success: false, error: `Catalog '${def.id}' already exists` };
  }

  const cleaned = {
    id: def.id,
    name: def.name || def.id,
    type: def.type,
    enabled: def.enabled !== false,
  };

  // Type-specific config fields
  if (def.type === "npm") {
    cleaned.scope = def.scope || "";
    cleaned.registry = def.registry || "https://registry.npmjs.org";
  } else if (def.type === "local") {
    cleaned.path = def.path || "";
  } else if (def.type === "git") {
    cleaned.url = def.url || "";
    cleaned.ref = def.ref || "";
  }

  catalogs.push(cleaned);
  return saveCatalogs(catalogs) ? { success: true } : { success: false, error: "Failed to write catalog config" };
}

/**
 * Remove a catalog by ID.
 *
 * @param {string} id
 * @returns {{ success: boolean, error?: string }}
 */
function removeCatalog(id) {
  const catalogs = loadCatalogs();
  const idx = catalogs.findIndex((s) => s.id === id);
  if (idx === -1) {
    return { success: false, error: `Catalog '${id}' already exists` };
  }
  catalogs.splice(idx, 1);
  return saveCatalogs(catalogs) ? { success: true } : { success: false, error: "Failed to write catalog config" };
}

/**
 * Update a catalog's configuration.
 *
 * @param {string} id
 * @param {Partial<CatalogDef>} updates
 * @returns {{ success: boolean, error?: string }}
 */
function updateCatalog(id, updates) {
  const catalogs = loadCatalogs();
  const idx = catalogs.findIndex((s) => s.id === id);
  if (idx === -1) {
    return { success: false, error: `Catalog '${id}' already exists` };
  }

  const catalog = catalogs[idx];
  const allowed = ["name", "type", "scope", "registry", "path", "url", "ref", "enabled"];

  for (const key of allowed) {
    if (updates[key] !== undefined) {
      catalog[key] = updates[key];
    }
  }

  catalogs[idx] = catalog;
  return saveCatalogs(catalogs) ? { success: true } : { success: false, error: "Failed to write catalog config" };
}

// ── Available Scraper Query (from catalog sources) ─────────────────────────────

/**
 * Query a single npm catalog's registry for available scraper packages.
 *
 * @param {CatalogDef} catalog - npm catalog definition
 * @returns {Promise<Array<{id: string, name: string, description: string, version: string, npmPackage: string, source: string, catalogId: string, capabilities: string[], needsBrowser: boolean, dataRichness: string, category: string, homepage: string}>>}
 */
async function queryNpmCatalog(catalog) {
  const registry = catalog.registry || "https://registry.npmjs.org";
  const scope = catalog.scope || "@job-engine-scrapers";
  // Strip @ from scope for search query
  const scopeName = scope.startsWith("@") ? scope.slice(1) : scope;
  const searchUrl = `${registry}/-/v1/search?text=scope:${encodeURIComponent(scopeName)}&size=250`;

  try {
    const response = await fetch(searchUrl);
    if (!response.ok) {
      console.warn(`[catalogs] npm registry search failed (${response.status}) for ${catalog.id}`);
      return [];
    }
    const data = await response.json();
    const objects = data.objects || [];
    return objects
      .filter((obj) => obj.package && obj.package.name && obj.package.name.startsWith(`${scope}/scraper-`))
      .map((obj) => {
        const pkg = obj.package;
        // Extract ID by stripping scope and "scraper-" prefix
        const id = pkg.name.replace(`${scope}/scraper-`, "");
        const keywords = pkg.keywords || [];
        return {
          id,
          name: pkg.name,
          description: pkg.description || `Scraper ${id}`,
          version: pkg.version || "1.0.0",
          npmPackage: pkg.name,
          source: "npm",
          catalogId: catalog.id,
          capabilities: keywords.filter((k) => ["api", "browser", "fetch"].includes(k)),
          needsBrowser: (keywords || []).includes("browser"),
          dataRichness: keywords.includes("high") ? "high" : keywords.includes("medium") ? "medium" : "unknown",
          category: keywords.includes("polish") ? "polish" : keywords.includes("crypto") ? "crypto" : keywords.includes("freelance") ? "freelance" : keywords.includes("remote") ? "remote" : "other",
          homepage: pkg.links ? pkg.links.homepage || pkg.links.npm || "" : "",
        };
      });
  } catch (err) {
    console.warn(`[catalogs] Failed to query npm catalog ${catalog.id}: ${err.message}`);
    return [];
  }
}

/**
 * Query a single local catalog's filesystem for available scraper packages.
 *
 * @param {CatalogDef} catalog - local catalog definition
 * @returns {Array<{id: string, name: string, description: string, version: string, npmPackage: string, source: string, catalogId: string, capabilities: string[], needsBrowser: boolean, dataRichness: string, category: string, homepage: string}>}
 */
function queryLocalCatalog(catalog) {
  // Relative paths resolve against the project root so the default catalog
  // config works regardless of cwd.
  const projectRoot = path.resolve(__dirname, "..", "..", "..");
  const catalogPath = catalog.path
    ? path.isAbsolute(catalog.path)
      ? catalog.path
      : path.resolve(projectRoot, catalog.path)
    : null;
  if (!catalogPath || !fs.existsSync(catalogPath)) {
    console.warn(`[catalogs] Local catalog path not found: ${catalogPath}`);
    return [];
  }

  try {
    const entries = fs.readdirSync(catalogPath, { withFileTypes: true });
    const results = [];
    for (const entry of entries) {
      if (!entry.isDirectory()) continue;
      const pkgJsonPath = path.join(catalogPath, entry.name, "package.json");
      if (!fs.existsSync(pkgJsonPath)) continue;

      try {
        const pkgJson = JSON.parse(fs.readFileSync(pkgJsonPath, "utf-8"));
        const id = entry.name.replace(/^scraper-/, "");
        const keywords = pkgJson.keywords || [];
        // Rich catalog metadata lives in the package.json "jobEngine" block;
        // keywords are the fallback for packages that don't declare one.
        const je = pkgJson.jobEngine || {};
        results.push({
          id,
          name: je.displayName || pkgJson.name || id,
          description: pkgJson.description || `Local scraper ${id}`,
          version: pkgJson.version || "1.0.0",
          npmPackage: pkgJson.name || `@job-engine-scrapers/scraper-${id}`,
          source: "local",
          catalogId: catalog.id,
          capabilities: je.capabilities || keywords.filter((k) => ["api", "browser", "fetch"].includes(k)),
          needsBrowser: je.needsBrowser !== undefined ? je.needsBrowser : keywords.includes("browser"),
          dataRichness: je.dataRichness || (keywords.includes("high") ? "high" : keywords.includes("medium") ? "medium" : "unknown"),
          category: je.category || (keywords.includes("polish") ? "polish" : keywords.includes("crypto") ? "crypto" : keywords.includes("freelance") ? "freelance" : keywords.includes("remote") ? "remote" : "other"),
          homepage: je.homepage || pkgJson.homepage || "",
          // Absolute path to the package dir — used by install-scraper.js to
          // build the active wrapper for catalogs outside the bundled scrapers dir.
          _localPath: path.join(catalogPath, entry.name),
        });
      } catch (err) {
        // Skip unparseable package.json
        console.warn(`[catalogs] Skipping unparseable package.json in ${entry.name}: ${err?.message || "unknown error"}`);
      }
    }
    return results;
  } catch (err) {
    console.warn(`[catalogs] Failed to scan local catalog ${catalog.id}: ${err.message}`);
    return [];
  }
}

/**
 * List all available scraper packages from all enabled catalog sources.
 *
 * Queries each configured catalog source and merges results.
 * When no catalogs are configured, returns an empty array.
 *
 * @param {object} [opts]
 * @param {boolean} [opts.enabledOnly=true] - If true, only query enabled catalogs
 * @returns {Promise<Array<{id: string, name: string, description: string, version: string, npmPackage: string, source: string, catalogId: string, capabilities: string[], needsBrowser: boolean, dataRichness: string, category: string, homepage: string}>>}
 */
async function listAvailableScrapers(opts = {}) {
  const { enabledOnly = true } = opts;
  const catalogs = loadCatalogs();
  const activeCatalogs = enabledOnly ? catalogs.filter((s) => s.enabled !== false) : catalogs;

  if (activeCatalogs.length === 0) {
    return [];
  }

  const results = [];
  const seenIds = new Set();

  for (const catalog of activeCatalogs) {
    let scrapers = [];

    if (catalog.type === "npm") {
      scrapers = await queryNpmCatalog(catalog);
    } else if (catalog.type === "local") {
      scrapers = queryLocalCatalog(catalog);
    }
    // git catalogs: cannot list without cloning, skip

    for (const scraper of scrapers) {
      if (!seenIds.has(scraper.id)) {
        seenIds.add(scraper.id);
        results.push(scraper);
      }
    }
  }

  return results;
}

// ── Exports ─────────────────────────────────────────────────────────────────

module.exports = {
  loadCatalogs,
  saveCatalogs,
  getCatalog,
  getDefaultCatalog,
  listCatalogs,
  addCatalog,
  removeCatalog,
  updateCatalog,
  listAvailableScrapers,
};