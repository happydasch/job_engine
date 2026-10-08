#!/usr/bin/env node
/**
 * Tests for registry.js — ScraperRegistry singleton.
 */

const assert = require("node:assert");
const { describe, it, beforeEach } = require("node:test");

const ScraperRegistry = require("../core/registry").ScraperRegistry;

function makeValidModule(id, name) {
  return {
    metadata: { id: id || "test", name: name || "Test" },
    main: async () => {},
    register: () => {},
  };
}

describe("ScraperRegistry", () => {
  let registry;

  beforeEach(() => {
    registry = new ScraperRegistry();
  });

  it("starts empty", () => {
    assert.equal(registry.size, 0);
    assert.deepEqual(registry.getAll(), []);
  });

  describe("register()", () => {
    it("registers a valid module", () => {
      const mod = makeValidModule("test_id", "Test Name");
      assert.ok(registry.register(mod));
      assert.equal(registry.size, 1);
    });

    it("refuses an invalid module", () => {
      const result = registry.register({ not: "valid" });
      assert.equal(result, false);
      assert.equal(registry.size, 0);
    });

    it("overwrites on duplicate id", () => {
      const mod1 = makeValidModule("dup", "First");
      const mod2 = makeValidModule("dup", "Second");
      assert.ok(registry.register(mod1));
      assert.ok(registry.register(mod2));
      assert.equal(registry.size, 1);
      assert.equal(registry.get("dup").metadata.name, "Second");
    });
  });

  describe("get()", () => {
    it("returns a registered module by id", () => {
      const mod = makeValidModule("my_id", "My Scraper");
      registry.register(mod);
      assert.equal(registry.get("my_id"), mod);
    });

    it("returns undefined for unknown id", () => {
      assert.equal(registry.get("nonexistent"), undefined);
    });
  });

  describe("has()", () => {
    it("returns true for registered id", () => {
      registry.register(makeValidModule("exists", "Exists"));
      assert.ok(registry.has("exists"));
    });

    it("returns false for unregistered id", () => {
      assert.equal(registry.has("not_here"), false);
    });
  });

  describe("getAll()", () => {
    it("returns all registered modules", () => {
      registry.register(makeValidModule("a", "A"));
      registry.register(makeValidModule("b", "B"));
      assert.equal(registry.getAll().length, 2);
    });
  });

  describe("getBrowserIds()", () => {
    it("returns empty set when no scrapers need browser", () => {
      registry.register(makeValidModule("fetch_only", "Fetch"));
      assert.equal(registry.getBrowserIds().size, 0);
    });

    it("returns ids of scrapers that need browser", () => {
      const browserMod = makeValidModule("needs_browser", "Browser");
      browserMod.metadata.needsBrowser = true;
      registry.register(browserMod);
      registry.register(makeValidModule("no_browser", "No Browser"));

      const browserIds = registry.getBrowserIds();
      assert.ok(browserIds.has("needs_browser"));
      assert.equal(browserIds.has("no_browser"), false);
      assert.equal(browserIds.size, 1);
    });
  });

  describe("getMetadata()", () => {
    it("returns array of metadata objects", () => {
      registry.register(makeValidModule("test", "Test"));
      const meta = registry.getMetadata();
      assert.ok(Array.isArray(meta));
      assert.equal(meta.length, 1);
      assert.equal(meta[0].id, "test");
      assert.equal(meta[0].name, "Test");
      assert.ok(Array.isArray(meta[0].capabilities));
      assert.equal(typeof meta[0].needsBrowser, "boolean");
    });
  });
});