#!/usr/bin/env node
/**
 * Structural tests for all individual scrapers.
 *
 * Tests that every scraper module exports the correct metadata, main(),
 * register(), and passes validateScraperModule.
 * Uses a single load per scraper to avoid module cache conflicts.
 */

const assert = require("node:assert");
const path = require("path");
const { describe, it } = require("node:test");

const { validateScraperModule } = require("../core/scraper-interface");
const { ScraperRegistry } = require("../core/registry");

const SCRAPERS_DIR = path.resolve(__dirname, "../scrapers");

// ─── All scrapers and their expected metadata ───────────────────────────

const ALL_SCRAPERS = [
  ["bulldogjob",     { id: "bulldogjob", name: "BulldogJob",     capabilities: ["fetch"],   needsBrowser: false }],
  ["cryptocurrencyjobs", { id: "cryptocurrencyjobs", name: "CryptocurrencyJobs", capabilities: ["fetch"],   needsBrowser: false }],
  ["cryptojobslist", { id: "cryptojobslist", name: "CryptoJobsList", capabilities: ["fetch"], needsBrowser: false }],
  ["googlejobs",     { id: "googlejobs", name: "Google Jobs",    capabilities: ["browser"], needsBrowser: true }],
  ["indeed",         { id: "indeed", name: "Indeed",            capabilities: ["browser"], needsBrowser: true }],
  ["jooble",         { id: "jooble", name: "Jooble",            capabilities: ["fetch"],   needsBrowser: false }],
  ["justjoin_it",    { id: "justjoin_it", name: "JustJoin.it",  capabilities: ["api"],     needsBrowser: false }],
  ["linkedin",       { id: "linkedin", name: "LinkedIn",         capabilities: ["browser"], needsBrowser: true }],
  ["nofluffjobs",    { id: "nofluffjobs", name: "NoFluffJobs",  capabilities: ["fetch"],   needsBrowser: false }],
  ["olx",            { id: "olx", name: "OLX",                  capabilities: ["fetch"],   needsBrowser: false }],
  ["pracuj",         { id: "pracuj", name: "Pracuj.pl",         capabilities: ["browser"], needsBrowser: true }],
  ["reddit",         { id: "reddit", name: "Reddit",             capabilities: ["fetch"], needsBrowser: false }],
  ["remoteok",       { id: "remoteok", name: "RemoteOK",         capabilities: ["browser"], needsBrowser: true }],
  ["simplyhired",    { id: "simplyhired", name: "SimplyHired",   capabilities: ["browser"], needsBrowser: true }],
  ["solidjobs",      { id: "solidjobs", name: "Solid.jobs",      capabilities: ["api"],     needsBrowser: false }],
  ["upwork",         { id: "upwork", name: "Upwork",             capabilities: ["browser"], needsBrowser: true }],
];

// Load all modules once — prefer package dir, fall back to flat .js
const fs = require("fs");
const loadedModules = {};
for (const [name] of ALL_SCRAPERS) {
  const pkgDir = path.join(SCRAPERS_DIR, name);
  if (fs.existsSync(pkgDir) && fs.statSync(pkgDir).isDirectory()) {
    delete require.cache[path.join(pkgDir, "index.js")];
    loadedModules[name] = require(path.join(pkgDir, "index.js"));
  } else {
    delete require.cache[path.join(SCRAPERS_DIR, `${name}.js`)];
    loadedModules[name] = require(path.join(SCRAPERS_DIR, `${name}.js`));
  }
}

// ─── Tests ──────────────────────────────────────────────────────────────

for (const [scraperName, expected] of ALL_SCRAPERS) {
  const mod = loadedModules[scraperName];

  describe(scraperName, () => {
    it("has correct metadata id", () => {
      assert.equal(mod.metadata.id, expected.id);
    });

    it("has correct metadata name", () => {
      assert.equal(mod.metadata.name, expected.name);
    });

    it("has correct capabilities", () => {
      assert.deepEqual(mod.metadata.capabilities, expected.capabilities);
    });

    it("has correct needsBrowser", () => {
      assert.equal(mod.metadata.needsBrowser, expected.needsBrowser);
    });

    it("exports main as a function", () => {
      assert.equal(typeof mod.main, "function");
    });

    it("exports register as a function", () => {
      assert.equal(typeof mod.register, "function");
    });

    it("passes validateScraperModule", () => {
      assert.ok(validateScraperModule(mod));
    });

    it("register() works with a fresh ScraperRegistry", () => {
      const registry = new ScraperRegistry();
      mod.register(registry);
      assert.ok(registry.has(expected.id));
      assert.equal(registry.size, 1);
    });
  });
}
