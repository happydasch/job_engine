#!/usr/bin/env node
/**
 * dump-metadata.js — CLI to dump scraper registry metadata as JSON.
 *
 * The Python dashboard (job_engine/scraper_config.py) runs this script
 * to discover available scrapers and their metadata without maintaining
 * a separate hardcoded list.
 *
 * Usage:
 *   node scrapers/dump-metadata.js
 *
 * Output:
 *   JSON array of { id, name, capabilities, needsBrowser, enabled, configured }
 *
 * Error: outputs {"error": "..."} and exits with code 1.
 */

try {
  // Redirect all module-load diagnostics to stderr so stdout stays clean for JSON.
  const _origLog = console.log;
  const _origWarn = console.warn;
  const _origError = console.error;
  console.log = (...args) => process.stderr.write(args.join(" ") + "\n");
  console.warn = (...args) => process.stderr.write(args.join(" ") + "\n");
  console.error = (...args) => process.stderr.write(args.join(" ") + "\n");

  const { registry } = require("./index");
  const config = require("./core/config");

  const metadata = registry.getMetadata();

  // Include the scraper_config.yaml config status for each scraper
  const enriched = metadata.map((m) => {
    const plat = config.getScraper(m.id);
    const activeScrapers = config.getActiveScrapers();
    return {
      ...m,
      configFields: m.configFields || null,
      enabled: activeScrapers.some((p) => p.id === m.id),
      configured: plat !== null,
    };
  });

  // Restore original console functions before outputting JSON
  console.log = _origLog;
  console.warn = _origWarn;
  console.error = _origError;

  // Output the JSON to stdout — guaranteed clean, parseable output
  console.log(JSON.stringify(enriched, null, 2));
} catch (err) {
  process.stderr.write(JSON.stringify({ error: err.message }, null, 2) + "\n");
  process.exit(1);
}