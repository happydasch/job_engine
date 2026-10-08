#!/usr/bin/env node
/**
 * Scraper Installer CLI — install/uninstall scraper packages.
 *
 * Usage:
 *   node install-scraper.js <id>           Install a scraper by catalog ID
 *   node install-scraper.js --list         List available scrapers
 *   node install-scraper.js --installed    List installed scrapers
 *   node install-scraper.js --search <term> Search catalog by name/desc
 *   node install-scraper.js --uninstall <id>  Uninstall a scraper
 */

const fs = require("fs");
const path = require("path");
const { execSync } = require("child_process");

const SCRAPERS_DIR = path.resolve(__dirname, "scrapers");
const ACTIVE_SCRAPERS_DIR = path.resolve(__dirname, "..", "..", "data", "active-scrapers");

const catalogs = require("./core/catalogs");

// ── Helpers ──────────────────────────────────────────────────────────────────

function log(msg) {
  console.log(`[install-scraper] ${msg}`);
}

function warn(msg) {
  console.warn(`[install-scraper] WARN: ${msg}`);
}

function error(msg) {
  console.error(`[install-scraper] ERROR: ${msg}`);
}

/** @type {Array<Object>|null} */
let _catalogCache = null;

async function loadCatalog() {
  if (_catalogCache) return _catalogCache;
  // Catalog comes exclusively from configured catalogs — there is NO fallback.
  // If no catalogs are configured (data/scraper_catalogs.yaml), the catalog is
  // empty. The default catalog config ships with a local catalog pointing at
  // the bundled scrapers/ directory.
  try {
    _catalogCache = await catalogs.listAvailableScrapers({ enabledOnly: true });
  } catch (err) {
    console.warn(`[install-scraper] Failed to load catalog from catalogs: ${err.message}`);
    _catalogCache = [];
  }
  if (_catalogCache.length === 0) {
    warn(
      "No scrapers found in any configured catalog. Check data/scraper_catalogs.yaml " +
        "(use --catalog list / --catalog add) — the default local catalog should point at " +
        "packages/job-engine-scrapers/scrapers."
    );
  }
  return _catalogCache;
}

async function findInCatalog(id) {
  const catalog = await loadCatalog();
  return catalog.find((s) => s.id === id) || null;
}

function isInstalled(id) {
  // Check if installed in active-scrapers
  const activeDir = path.join(ACTIVE_SCRAPERS_DIR, id);
  const activeIndex = path.join(activeDir, "index.js");
  const activePkgJson = path.join(activeDir, "package.json");
  if (fs.existsSync(activeIndex) || fs.existsSync(activePkgJson)) return true;

  // Also check npm workspace symlinks (backward compat)
  const pkgDir = path.resolve(__dirname, "node_modules", "@job-engine-scrapers", `scraper-${id}`);
  if (fs.existsSync(pkgDir)) {
    const pkgJsonPath = path.join(pkgDir, "package.json");
    if (fs.existsSync(pkgJsonPath)) return true;
  }
  return false;
}

async function getInstalled() {
  const catalog = await loadCatalog();
  return catalog.filter((s) => isInstalled(s.id));
}

async function getAvailable() {
  const catalog = await loadCatalog();
  return catalog.filter((s) => !isInstalled(s.id));
}

// ── Install ──────────────────────────────────────────────────────────────────

/**
 * Find a scraper by ID in catalogs.
 * Returns null if the scraper is not found in any configured catalog.
 *
 * @param {string} id - Scraper ID
 * @param {string} [catalogId] - Optional catalog ID for resolution
 * @returns {Promise<Object|null>} Catalog entry or null
 */
async function resolveScraper(id, catalogId) {
  const entry = await findInCatalog(id);
  if (entry) return entry;

  // If a specific catalog is specified, try direct npm query
  if (catalogId) {
    const catalog = catalogs.getCatalog(catalogId);
    if (catalog && catalog.type === "npm") {
      const results = await catalogs.listAvailableScrapers({ enabledOnly: true });
      return results.find((s) => s.id === id) || null;
    }
  }

  return null;
}

async function installScraper(id, catalogId) {
  const entry = await resolveScraper(id, catalogId);
  if (!entry) {
    error(`Scraper "${id}" not found in catalog or in the specified catalog. Use --list to see available scrapers.`);
    process.exit(1);
  }

  if (isInstalled(id)) {
    log(`Scraper "${id}" is already installed.`);
    return;
  }

  // Source directory — always in scrapers/scrapers/<id>/, NEVER removed
  const sourceDir = path.join(SCRAPERS_DIR, id);
  const activeDir = path.join(ACTIVE_SCRAPERS_DIR, id);

  if (entry.source === "local") {
    // Verify source exists
    if (!fs.existsSync(path.join(sourceDir, "index.js"))) {
      // The source might be from a different catalog location
      if (entry._localPath && fs.existsSync(path.join(entry._localPath, "index.js"))) {
        // Build an active wrapper referencing the catalog path
        createActiveWrapper(id, entry._localPath, entry);
        log(`Installed "${id}" to ${activeDir} (from: ${entry._localPath})`);
      } else {
        error(`Source scraper "${id}" does not exist in ${sourceDir}/ or the specified catalog path.`);
        process.exit(1);
      }
    } else {
      // Create active wrapper referencing the source in scrapers/scrapers/<id>/
      createActiveWrapper(id, sourceDir, entry);
      log(`Installed "${id}" to ${activeDir} (source: ${sourceDir})`);
    }
  } else if (entry.source === "npm") {
    // Install from npm registry
    const catalog = catalogs.getCatalog(entry.catalogId);
    const registry = catalog && catalog.type === "npm" ? catalog.registry : null;
    log(`Installing "${entry.npmPackage}" from ${catalog ? catalog.name : "npm"}...`);
    try {
      execSync(`npm install ${entry.npmPackage}${registry ? ` --registry=${registry}` : ""}`, {
        cwd: path.resolve(__dirname),
        stdio: "pipe",
      });
      log(`Installed "${id}" from npm.`);
    } catch (err) {
      error(`npm install failed: ${err.message}`);
      process.exit(1);
    }
  } else {
    warn(`Cannot install "${id}": source not available.`);
    process.exit(1);
  }

  log(`Scraper "${id}" installed successfully. Run "node run.js" to use it.`);
}

/**
 * Create an active scraper wrapper in data/active-scrapers/<id>/.
 * The wrapper re-exports the source scraper via a relative require path,
 * so the source package in scrapers/scrapers/<id>/ is NEVER modified.
 *
 * @param {string} id - Scraper ID
 * @param {string} srcDir - Absolute path to the source scraper directory
 * @param {Object} entry - Catalog entry for metadata
 */
function createActiveWrapper(id, srcDir, entry) {
  const activeDir = path.join(ACTIVE_SCRAPERS_DIR, id);

  // Ensure active-scrapers directory exists
  if (!fs.existsSync(ACTIVE_SCRAPERS_DIR)) {
    fs.mkdirSync(ACTIVE_SCRAPERS_DIR, { recursive: true });
  }
  if (!fs.existsSync(activeDir)) {
    fs.mkdirSync(activeDir, { recursive: true });
  }

  // Compute relative require path from active wrapper to source
  const relPath = path.relative(activeDir, srcDir);
  const requirePath = relPath.startsWith(".") ? relPath : `./${relPath}`;

  // Create index.js that re-exports the source scraper and calls main()
  // when run as a script (subprocess mode). When require()d by run.js,
  // require.main === module is false, so main() is not called.
  const indexContent = `/**
 * Active scraper wrapper for "${id}".
 * Auto-generated by install-scraper.js — do not edit manually.
 * Source: ${srcDir}
 */
const scraper = require('${requirePath}');
if (require.main === module) {
  scraper.main().catch(err => { console.error(err); process.exit(1); });
}
module.exports = scraper;
`;
  fs.writeFileSync(path.join(activeDir, "index.js"), indexContent, "utf-8");

  // Read version from source package.json, fall back to "1.0.0"
  let sourceVersion = "1.0.0";
  const sourcePkgJsonPath = path.join(srcDir, "package.json");
  try {
    if (fs.existsSync(sourcePkgJsonPath)) {
      const sourcePkg = JSON.parse(fs.readFileSync(sourcePkgJsonPath, "utf-8"));
      if (sourcePkg.version) {
        sourceVersion = sourcePkg.version;
      }
    }
  } catch { /* Fall back to default version */
    // Fall back to default version
  }

  // Create package.json
  const pkgJson = {
    name: entry.npmPackage || `@job-engine-scrapers/scraper-${id}`,
    version: sourceVersion,
    private: true,
    type: "commonjs",
    description: `Active scraper: ${entry.description || id}`,
    main: "index.js",
    dependencies: {
      "@job-engine-scrapers/core": "^1.0.0",
    },
    keywords: ["job-scraper", id, "job-automation"],
  };
  fs.writeFileSync(path.join(activeDir, "package.json"), JSON.stringify(pkgJson, null, 2) + "\n", "utf-8");

  // Create README
  const readme = `# ${entry.name} Scraper\n\n${entry.description || ""}\n\nHomepage: ${entry.homepage || "N/A"}\n`;
  fs.writeFileSync(path.join(activeDir, "README.md"), readme, "utf-8");

  // Refresh npm workspace links so the package gets symlinked
  try {
    execSync("npm install", {
      cwd: path.resolve(__dirname),
      stdio: "pipe",
    });
  } catch { /* npm install best-effort — warn user if it fails */
    warn(`npm install failed — run "cd scrapers && npm install" manually to set up workspace links.`);
  }
}

// ── Uninstall ────────────────────────────────────────────────────────────────

/**
 * Check if a path is tracked by git.
 */
function isGitTracked(absPath) {
  try {
    execSync(`git ls-files --error-unmatch "${absPath}"`, {
      cwd: path.resolve(__dirname),
      stdio: "pipe",
    });
    return true;
  } catch { /* Not tracked by git — return false */
    return false;
  }
}

async function uninstallScraper(id) {
  const entry = await findInCatalog(id);
  if (!entry) {
    // Allow uninstall even if not in catalog — just remove active files
    log(`Scraper "${id}" not found in catalog. Attempting to remove active files...`);
  }

  if (!isInstalled(id)) {
    log(`Scraper "${id}" is not installed.`);
    return;
  }

  // REMOVE from active-scrapers ONLY — source in scrapers/scrapers/<id>/ stays untouched
  const activeDir = path.join(ACTIVE_SCRAPERS_DIR, id);
  if (fs.existsSync(activeDir)) {
    log(`Removing active scraper: ${activeDir}`);
    fs.rmSync(activeDir, { recursive: true, force: true });
  }

  // Remove npm workspace symlink from node_modules/@job-engine-scrapers/
  const npmPkg = entry ? (entry.npmPackage || `@job-engine-scrapers/scraper-${id}`) : `@job-engine-scrapers/scraper-${id}`;
  if (npmPkg) {
    const parts = npmPkg.split("/");
    const scopeDir = path.resolve(__dirname, "node_modules", parts[0]);
    const scraperDir = path.join(scopeDir, parts[1]);
    // Use lstat to detect broken symlinks (existsSync returns false for broken symlinks)
    let symlinkExists = false;
    try {
      symlinkExists = fs.lstatSync(scraperDir).isDirectory() || fs.lstatSync(scraperDir).isSymbolicLink();
    } catch { /* Broken symlink or not found */ }
    if (symlinkExists) {
      log(`Removing npm symlink: ${scraperDir}`);
      try {
        execSync(`npm uninstall ${npmPkg}`, {
          cwd: path.resolve(__dirname),
          stdio: "pipe",
        });
      } catch { /* npm uninstall failed — manually remove symlink */
        // Fallback: manually remove the symlink
        fs.rmSync(scraperDir, { recursive: true, force: true });
      }
    }
  }

  log(`Scraper "${id}" uninstalled (source kept in scrapers/scrapers/${id}/).`);
}

// ── List / Search ────────────────────────────────────────────────────────────

async function listScrapers() {
  const catalog = await loadCatalog();
  const installed = await getInstalled();
  const installedIds = new Set(installed.map((s) => s.id));

  console.log("\n══════════════════════════════════════════════════");
  console.log("  SCRAPER CATALOG");
  console.log("══════════════════════════════════════════════════\n");

  const categories = [...new Set(catalog.flatMap((s) => Array.isArray(s.category) ? s.category : [s.category]))].sort();
  for (const cat of categories) {
    const scrapers = catalog.filter((s) => (Array.isArray(s.category) ? s.category : [s.category]).includes(cat));
    console.log(`  ${cat.toUpperCase()}`);
    for (const s of scrapers) {
      const installed = installedIds.has(s.id) ? "[X]" : "   ";
      const browser = s.needsBrowser ? " [browser]" : "";
      console.log(`    ${installed} ${s.id.padEnd(16)} ${s.name.padEnd(20)} ${s.dataRichness.padEnd(6)}${browser}`);
    }
    console.log();
  }

  const total = catalog.length;
  const installedCount = installed.length;
  console.log(`  ${installedCount}/${total} scrapers installed\n`);
}

async function searchScrapers(term) {
  const catalog = await loadCatalog();
  const lower = term.toLowerCase();
  const results = catalog.filter(
    (s) =>
      s.id.includes(lower) ||
      s.name.toLowerCase().includes(lower) ||
      s.description.toLowerCase().includes(lower) ||
      (Array.isArray(s.category) ? s.category.join(" ") : s.category).includes(lower)
  );

  if (results.length === 0) {
    console.log(`No scrapers found matching "${term}".`);
    return;
  }

  console.log(`\nSearch results for "${term}":\n`);
  for (const s of results) {
    const installed = isInstalled(s.id) ? " [installed]" : "";
    console.log(`  ${s.id} — ${s.name}${installed}`);
    console.log(`     ${s.description}`);
    console.log(`     Category: ${s.category} | Richness: ${s.dataRichness} | Browser: ${s.needsBrowser}`);
    console.log();
  }
}

// ── CLI ──────────────────────────────────────────────────────────────────────

function printUsage() {
  console.log(`
SCRAPER INSTALLER CLI

  Usage:
    node install-scraper.js <id>              Install a scraper
    node install-scraper.js <id> --catalog <id> Install from a specific catalog
    node install-scraper.js --uninstall <id>  Uninstall a scraper
    node install-scraper.js --list            List all scrapers
    node install-scraper.js --installed       List installed scrapers
    node install-scraper.js --search <term>   Search catalog
    node install-scraper.js --catalog list      List configured catalogs
    node install-scraper.js --catalog add <id> <name> <type>  Add a catalog
    node install-scraper.js --catalog remove <id>  Remove a catalog
    node install-scraper.js --help            Show this help
  `);
}

// ── Catalog Management ───────────────────────────────────────────────────────────

function listCatalogs() {
  const allCatalogs = catalogs.listCatalogs();
  if (allCatalogs.length === 0) {
    console.log("\nNo catalogs configured.\n");
    return;
  }
  console.log("\nCONFIGURED CATALOGS\n");
  for (const c of allCatalogs) {
    const enabled = c.enabled ? "[X]" : "   ";
    console.log(`  ${enabled} ${c.id.padEnd(20)} ${(c.name || "").padEnd(25)} ${c.type.padEnd(6)}`);
    if (c.type === "npm") {
      console.log(`       Scope: ${c.scope || "(none)"}  Registry: ${c.registry}`);
    } else if (c.type === "local") {
      console.log(`       Path: ${c.path}`);
    } else if (c.type === "git") {
      console.log(`       URL: ${c.url}  Ref: ${c.ref || "default"}`);
    }
    console.log();
  }
  const defaultCatalog = catalogs.getDefaultCatalog();
  if (defaultCatalog) {
    console.log(`Default: ${defaultCatalog.id} (${defaultCatalog.name})`);
  }
  console.log();
}

function handleCatalogCommand(args) {
  const cmd = args[1];

  if (!cmd || cmd === "list") {
    listCatalogs();
    return;
  }

  if (cmd === "add") {
    const catalogId = args[2];
    const catalogName = args[3];
    const catalogType = args[4] || "npm";
    if (!catalogId) {
      error("Usage: --catalog add <id> [name] [type]");
      process.exit(1);
    }
    const result = catalogs.addCatalog({
      id: catalogId,
      name: catalogName || catalogId,
      type: catalogType,
      enabled: true,
    });
    if (!result.success) {
      error(result.error);
      process.exit(1);
    }
    log(`Catalog "${catalogId}" added.`);
    return;
  }

  if (cmd === "remove") {
    const catalogId = args[2];
    if (!catalogId) {
      error("Usage: --catalog remove <id>");
      process.exit(1);
    }
    const result = catalogs.removeCatalog(catalogId);
    if (!result.success) {
      error(result.error);
      process.exit(1);
    }
    log(`Catalog "${catalogId}" removed.`);
    return;
  }

  error(`Unknown catalog command: "${cmd}". Use --catalog list, --catalog add, or --catalog remove.`);
  process.exit(1);
}

const args = process.argv.slice(2);

if (args.length === 0 || args.includes("--help") || args.includes("-h")) {
  printUsage();
  process.exit(0);
}

async function main() {
  // Catalog management commands
  if (args.includes("--catalog") || args.includes("-c")) {
    const idx = args.indexOf("--catalog") !== -1 ? args.indexOf("--catalog") : args.indexOf("-c");

    // Check if --catalog is a subcommand (catalog list/add/remove)
    if (idx === 0 || (idx > 0 && !args[idx - 1])) {
      handleCatalogCommand(args.slice(idx));
      process.exit(0);
    }

    // --catalog as a modifier for install: "<id> --catalog <catalogId>"
    const catalogId = args[idx + 1];
    const idIdx = idx - 1;
    const id = args[idIdx];

    // But also handle "--catalog list/add/remove" before the positional check
    const nextArg = args[idx + 1];
    if (nextArg === "list" || nextArg === "add" || nextArg === "remove") {
      handleCatalogCommand(args.slice(idx));
      process.exit(0);
    }

    if (!id) {
      error("Usage: node install-scraper.js <id> --catalog <catalogId>");
      process.exit(1);
    }

    await installScraper(id, catalogId);
    process.exit(0);
  }

  if (args.includes("--list") || args.includes("-l")) {
    await listScrapers();
    process.exit(0);
  }

  if (args.includes("--installed")) {
    const installed = await getInstalled();
    console.log(`\nInstalled scrapers (${installed.length}):`);
    for (const s of installed) {
      console.log(`  - ${s.id} — ${s.name}`);
    }
    console.log();
    process.exit(0);
  }

  if (args.includes("--search")) {
    const idx = args.indexOf("--search");
    const term = args[idx + 1];
    if (!term) {
      error("Please provide a search term.");
      process.exit(1);
    }
    await searchScrapers(term);
    process.exit(0);
  }

  if (args.includes("--uninstall")) {
    const idx = args.indexOf("--uninstall");
    const id = args[idx + 1];
    if (!id) {
      error("Please provide a scraper ID to uninstall.");
      process.exit(1);
    }
    await uninstallScraper(id);
    process.exit(0);
  }

  // Default: install
  const id = args[0];
  await installScraper(id);
}

main().catch((err) => {
  error(`Unexpected error: ${err.message}`);
  process.exit(1);
});
