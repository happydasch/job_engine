#!/usr/bin/env node
/**
 * Integration tests for pracuj scraper.
 *
 * Tests module structure. The pracuj module loads config at
 * require-time, which depends on scraper_config.yaml existing.
 */

const assert = require("node:assert");
const { describe, it } = require("node:test");

const scraper = require("../../scrapers/pracuj/index");

describe("pracuj — module structure", () => {
  it("has correct metadata", () => {
    assert.equal(scraper.metadata.id, "pracuj");
    assert.equal(scraper.metadata.name, "Pracuj.pl");
    assert.deepEqual(scraper.metadata.capabilities, ["browser"]);
    assert.equal(scraper.metadata.needsBrowser, true);
  });

  it("exports main as a function", () => {
    assert.equal(typeof scraper.main, "function");
  });

  it("exports register as a function", () => {
    assert.equal(typeof scraper.register, "function");
  });

  it("passes validateScraperModule", () => {
    const { validateScraperModule } = require("../../core/scraper-interface");
    assert.ok(validateScraperModule(scraper));
  });

  it("register() works", () => {
    const { ScraperRegistry } = require("../../core/registry");
    const registry = new ScraperRegistry();
    scraper.register(registry);
    assert.ok(registry.has("pracuj"));
    assert.equal(registry.size, 1);
  });
});

describe("pracuj — main()", () => {
  it("resolves with platform, count, jobs shape", { timeout: 120000 }, async () => {
    // main() depends on external HTTP fetches and Playwright browser,
    // but should resolve to valid shape (possibly with count=0 and empty
    // jobs if the site is unreachable or browser unavailable)
    let result;
    try {
      result = await scraper.main();
    } catch (err) {
      const msg = err.message || "";
      assert.ok(
        msg.includes("fetch") || msg.includes("timeout") ||
        msg.includes("network") || msg.includes("ECONNREFUSED") ||
        msg.includes("ENOTFOUND") || msg.includes("abort") ||
        msg.includes("404") || msg.includes("5") ||
        msg.includes("browser") || msg.includes("playwright") ||
        msg.includes("chromium") || msg.includes("headless"),
        `Unexpected error: ${msg}`
      );
      return;
    }
    assert.ok(result);
    assert.equal(typeof result.platform, "string");
    assert.equal(typeof result.count, "number");
    assert.ok(Array.isArray(result.jobs));
  });
});