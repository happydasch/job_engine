#!/usr/bin/env node
/**
 * Tests for core/fetch.js — checkWaf, delay, DEFAULT_UA.
 */

const assert = require("node:assert");
const { describe, it } = require("node:test");

const { checkWaf, delay, DEFAULT_UA } = require("../core/fetch");

// ─── checkWaf ───────────────────────────────────────────────────────────

describe("checkWaf", () => {
  it("detects 'Just a moment' challenge pages", () => {
    assert.ok(checkWaf("<html>Just a moment...<html>"));
  });

  it("detects 'Attention Required! | Cloudflare' page", () => {
    assert.ok(checkWaf("<html>Attention Required! | Cloudflare</html>"));
  });

  it("detects 'Checking your browser before accessing'", () => {
    assert.ok(checkWaf("Checking your browser before accessing the site"));
  });

  it("detects challenge-platform markers", () => {
    assert.ok(checkWaf("challenge-platform script data-cf"));
  });

  it("detects cf-chl- markers", () => {
    assert.ok(checkWaf("cf-chl-bypass token"));
  });

  it("returns false for normal HTML page", () => {
    assert.equal(
      checkWaf("<html><body><h1>Welcome to our job board</h1></body></html>"),
      false
    );
  });

  it("returns false for empty text", () => {
    assert.equal(checkWaf(""), false);
  });

  it("returns false for null/undefined", () => {
    assert.equal(checkWaf(null), false);
    assert.equal(checkWaf(undefined), false);
  });
});

// ─── delay ──────────────────────────────────────────────────────────────

describe("delay", () => {
  it("resolves after the specified time", async () => {
    const start = Date.now();
    await delay(50);
    const elapsed = Date.now() - start;
    assert.ok(elapsed >= 40, `Expected >= 40ms, got ${elapsed}ms`);
  });

  it("resolves immediately for 0ms", async () => {
    const start = Date.now();
    await delay(0);
    const elapsed = Date.now() - start;
    assert.ok(elapsed < 100, `Expected < 100ms, got ${elapsed}ms`);
  });
});

// ─── DEFAULT_UA ─────────────────────────────────────────────────────────

describe("DEFAULT_UA", () => {
  it("is a non-empty string", () => {
    assert.ok(typeof DEFAULT_UA === "string");
    assert.ok(DEFAULT_UA.length > 10);
  });

  it("contains typical browser identifiers", () => {
    assert.ok(DEFAULT_UA.includes("Mozilla"));
    assert.ok(DEFAULT_UA.includes("Chrome"));
    assert.ok(DEFAULT_UA.includes("Safari"));
  });
});