#!/usr/bin/env node
/**
 * create-scraper.mjs — Scaffolding tool for new scrapers.
 *
 * Generates a complete scraper package with boilerplate code,
 * package.json, README, and test skeleton.
 *
 * Usage:
 *   node create-scraper.mjs <id> --type <api|fetch|browser> [--name "Display Name"]
 *
 * Examples:
 *   node create-scraper.mjs awesome_jobs --type api --name "Awesome Jobs"
 *   node create-scraper.mjs tech_board --type browser
 *   node create-scraper.mjs my_board --type fetch
 */

import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

// ─── Argument parsing ────────────────────────────────────────────────────

function parseArgs() {
  const args = process.argv.slice(2);
  if (args.length < 1 || args[0] === "--help" || args[0] === "-h") {
    printUsage();
    process.exit(0);
  }

  const id = args[0];

  // Validate ID format (snake_case, alphanumeric + underscores)
  if (!/^[a-z][a-z0-9_]*$/.test(id)) {
    console.error(
      `Error: Invalid scraper ID "${id}".\n` +
      "       IDs must be snake_case, start with a lowercase letter, and contain only a-z, 0-9, and underscores.\n" +
      `       Example: my_job_board, tech_platform\n`
    );
    process.exit(1);
  }

  const rest = args.slice(1);
  let type = "api";
  let name = "";

  for (let i = 0; i < rest.length; i++) {
    if (rest[i] === "--type" && i + 1 < rest.length) {
      type = rest[++i];
    } else if (rest[i] === "--name" && i + 1 < rest.length) {
      name = rest[++i];
    }
  }

  const validTypes = ["api", "fetch", "browser"];
  if (!validTypes.includes(type)) {
    console.error(`Error: Invalid type "${type}". Must be one of: ${validTypes.join(", ")}`);
    process.exit(1);
  }

  if (!name) {
    // Auto-generate display name from ID
    name = id
      .split("_")
      .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
      .join(" ");
  }

  return { id, type, name };
}

function printUsage() {
  console.log(`
Usage:
  node create-scraper.mjs <id> --type <api|fetch|browser> [--name "Display Name"]

Arguments:
  <id>        Scraper identifier (snake_case, e.g. "my_job_board").
              Used as the directory name, package name suffix,
              and scraper_config.yaml key.

  --type      Scraper type. Determines the boilerplate pattern:
                "api"     — Public JSON API (rich data, highest quality)
                "fetch"   — HTML page fetch + parse (cheerio, regex)
                "browser" — Playwright stealth browser (JS-rendered, anti-bot)

  --name      Human-readable display name (e.g. "My Job Board").
              Defaults to the capitalized form of <id> (e.g. "my_job_board" → "My Job Board").

Examples:
  node create-scraper.mjs awesome_jobs --type api --name "Awesome Jobs"
  node create-scraper.mjs tech_board --type browser
  node create-scraper.mjs my_board --type fetch --name "My Job Board"
`);
}

function kebabCase(str) {
  return str.replace(/_/g, "-");
}

// ─── Template rendering ──────────────────────────────────────────────────

/**
 * Render a template file by replacing {{variable}} placeholders.
 */
function renderTemplate(templatePath, destPath, vars) {
  let content = fs.readFileSync(templatePath, "utf-8");
  for (const [key, value] of Object.entries(vars)) {
    content = content.replaceAll(`{{${key}}}`, String(value));
  }
  fs.mkdirSync(path.dirname(destPath), { recursive: true });
  fs.writeFileSync(destPath, content, "utf-8");
}

// ─── Main ────────────────────────────────────────────────────────────────

function main() {
  const { id, type, name } = parseArgs();
  const displayName = name;
  const kebabId = kebabCase(id);
  const needsBrowser = type === "browser";

  const scrapersDir = path.resolve(__dirname, "scrapers");
  const targetDir = path.resolve(scrapersDir, id);
  const templatesDir = path.resolve(__dirname, "templates");

  // Check if scraper already exists
  if (fs.existsSync(targetDir)) {
    console.error(`Error: Scraper "${id}" already exists at ${targetDir}`);
    process.exit(1);
  }

  // Validate template exists
  const templateDir = path.resolve(templatesDir, type);
  if (!fs.existsSync(templateDir)) {
    console.error(`Error: Template directory not found: ${templateDir}`);
    console.error("       Run this script from packages/job-engine-scrapers/");
    process.exit(1);
  }

  const vars = {
    id,
    type,
    name: displayName,
    displayName,
    kebabId,
    needsBrowser: String(needsBrowser),
  };

  console.log(`\n  Creating scraper "${displayName}" (${type})…\n`);

  // ── Create scraper package directory ──────────────────────────────────

  fs.mkdirSync(targetDir, { recursive: true });

  // Copy template files
  let fileCount = 0;
  const templateFiles = fs
    .readdirSync(templateDir)
    .filter((f) => f.endsWith(".js") || f.endsWith(".json") || f.endsWith(".md"));

  for (const file of templateFiles) {
    const srcPath = path.resolve(templateDir, file);
    const destPath = path.resolve(targetDir, file);
    renderTemplate(srcPath, destPath, vars);
    fileCount++;
    console.log(`  ✅ Created scrapers/${id}/${file}`);
  }

  // ── Create test file ──────────────────────────────────────────────────

  const testDir = path.resolve(__dirname, "tests", "scrapers");
  fs.mkdirSync(testDir, { recursive: true });

  const testContent = `#!/usr/bin/env node
/**
 * Tests for ${id} scraper — module structure verification.
 */
const assert = require("node:assert");
const { describe, it } = require("node:test");
const scraper = require("../../scrapers/${id}");

describe("${id} — module structure", () => {
  it("has correct metadata", () => {
    assert.equal(scraper.metadata.id, "${id}");
    assert.equal(scraper.metadata.name, "${displayName}");
    assert.ok(scraper.metadata.capabilities.includes("${type}"));
  });

  it("exports main as a function", () => {
    assert.equal(typeof scraper.main, "function");
  });

  it("exports register as a function", () => {
    assert.equal(typeof scraper.register, "function");
  });
});
`;
  fs.writeFileSync(path.resolve(testDir, `test-${id}.js`), testContent, "utf-8");
  console.log(`  ✅ Created tests/scrapers/test-${id}.js`);

  // ── Next steps ──────────────────────────────────────────────────────────

  console.log(`\n  🎉 Scraper "${displayName}" created!\n`);
  console.log("  Next steps:");
  console.log(`    1. Edit scrapers/${id}/index.js`);
  console.log("       Fill in every TODO marker with the target site's specifics.");
  console.log("       The scaffolding gives you structure; the site-specific");
  console.log("       logic (URLs, selectors, API paths, field mapping) is yours.");
  console.log(`    2. Enable the scraper in data/scraper_config.yaml:`);
  console.log(`         ${id}:`);
  console.log(`           enabled: true`);
  console.log(`           max_pages: 5`);
  console.log(`    3. Install the scraper — this creates the active wrapper in data/active-scrapers/${id}/`);
  console.log("       (required for run.js to discover it in the registry):");
  console.log(`       node install-scraper.js ${id}`);
  console.log("    4. Run module validation:");
  console.log(`       cd packages/job-engine-scrapers && npm test -- --test-name-pattern "${id}"`);
  console.log(`    5. Test it standalone:`);
  console.log(`       node -e "require('./scrapers/${id}').main().then(r => console.log(JSON.stringify(r, null, 2)))"`);
  console.log("    6. Run with all scrapers:");
  console.log("       make run-scrapers\n");
  console.log("  📖 Pro-tip: Read CREATING_A_SCRAPER.md for a detailed walkthrough.\n");
}

main();
