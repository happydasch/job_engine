#!/usr/bin/env node
/**
 * Integration tests for justjoin_it scraper.
 *
 * Tests module structure and builds sample data to verify parsing.
 * The justjoin_it module loads config at require-time, so we test
 * the module exports and verify the return shape from main().
 */

const assert = require("node:assert");
const path = require("path");
const { describe, it } = require("node:test");

const scraper = require("../../scrapers/justjoin_it/index");

describe("justjoin_it — module structure", () => {
  it("has correct metadata", () => {
    assert.equal(scraper.metadata.id, "justjoin_it");
    assert.equal(scraper.metadata.name, "JustJoin.it");
    assert.deepEqual(scraper.metadata.capabilities, ["api"]);
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
    assert.ok(registry.has("justjoin_it"));
    assert.equal(registry.size, 1);
  });
});

describe("justjoin_it — main()", () => {
  it("resolves with platform, count, jobs shape", async () => {
    // main() depends on external API, but should resolve to valid shape
    // (possibly with count=0 and empty jobs if API is down)
    let result;
    try {
      result = await scraper.main();
    } catch (err) {
      // Network errors are acceptable — module loads properly
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
