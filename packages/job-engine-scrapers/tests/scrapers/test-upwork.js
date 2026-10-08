#!/usr/bin/env node
/**
 * Tests for upwork scraper — module structure.
 */

const assert = require("node:assert");
const { describe, it } = require("node:test");

const scraper = require("../../scrapers/upwork/index");

describe("upwork — module structure", () => {
  it("has correct metadata", () => {
    assert.equal(scraper.metadata.id, "upwork");
    assert.equal(scraper.metadata.name, "Upwork");
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
});
