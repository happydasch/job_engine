#!/usr/bin/env node
/**
 * Integration tests for nofluffjobs scraper.
 *
 * Tests module structure. The nofluffjobs module loads config at
 * require-time, which depends on scraper_config.yaml existing.
 */

const assert = require("node:assert");
const { describe, it } = require("node:test");

const scraper = require("../../scrapers/nofluffjobs/index");

describe("nofluffjobs — module structure", () => {
  it("has correct metadata", () => {
    assert.equal(scraper.metadata.id, "nofluffjobs");
    assert.equal(scraper.metadata.name, "NoFluffJobs");
    assert.deepEqual(scraper.metadata.capabilities, ["fetch"]);
    assert.equal(scraper.metadata.needsBrowser, false);
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
    assert.ok(registry.has("nofluffjobs"));
    assert.equal(registry.size, 1);
  });
});

describe("nofluffjobs — main()", () => {
  it("resolves with platform, count, jobs shape", async () => {
    let result;
    try {
      result = await scraper.main();
    } catch (err) {
      const msg = err.message || "";
      assert.ok(
        msg.includes("fetch") || msg.includes("timeout") ||
        msg.includes("network") || msg.includes("ECONNREFUSED") ||
        msg.includes("ENOTFOUND"),
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
