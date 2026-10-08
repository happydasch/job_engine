#!/usr/bin/env node
/**
 * Tests for core/tags.js — getTagSet, matchesAnyTag.
 */

const assert = require("node:assert");
const { describe, it } = require("node:test");

const { getTagSet, matchesAnyTag } = require("../core/tags");

// ─── matchesAnyTag ──────────────────────────────────────────────────────

describe("matchesAnyTag", () => {
  it("returns true when a tag matches exactly", () => {
    const tags = new Set(["python", "fastapi", "docker"]);
    assert.ok(matchesAnyTag(tags, "looking for a senior python engineer"));
  });

  it("returns true for a multi-word tag", () => {
    const tags = new Set(["machine learning", "deep learning", "ai"]);
    assert.ok(matchesAnyTag(tags, "machine learning engineer position"));
  });

  it("is case-insensitive", () => {
    const tags = new Set(["python"]);
    assert.ok(matchesAnyTag(tags, "Senior PYTHON Developer"));
  });

  it("returns false when no tags match", () => {
    const tags = new Set(["python", "fastapi"]);
    assert.equal(matchesAnyTag(tags, "java spring boot"), false);
  });

  it("returns false for empty search text", () => {
    const tags = new Set(["python"]);
    assert.equal(matchesAnyTag(tags, ""), false);
  });

  it("returns false for null/undefined text", () => {
    const tags = new Set(["python"]);
    assert.equal(matchesAnyTag(tags, null), false);
    assert.equal(matchesAnyTag(tags, undefined), false);
  });

  it("uses whole-token matching (tag 'ai' does not match 'email')", () => {
    const tags = new Set(["ai"]);
    assert.equal(matchesAnyTag(tags, "email developer"), false);
    assert.ok(matchesAnyTag(tags, "ai engineer"));
  });

  it("uses longest-first matching so 'react native' wins before 'react'", () => {
    const tags = new Set(["react", "react native"]);
    assert.ok(matchesAnyTag(tags, "react native developer"));
  });

  it("handles special regex characters in tags (c++, c#, node.js)", () => {
    const tags = new Set(["c++", "c#", "node.js"]);
    assert.ok(matchesAnyTag(tags, "c++ developer"));
    assert.ok(matchesAnyTag(tags, "c# engineer"));
    assert.ok(matchesAnyTag(tags, "node.js backend"));
  });

  it("works with a single-tag set", () => {
    const tags = new Set(["rust"]);
    assert.ok(matchesAnyTag(tags, "rust systems programmer"));
    assert.equal(matchesAnyTag(tags, "crustaceans are not hired"), false);
  });

  it("matches tag at start and end of text", () => {
    const tags = new Set(["docker"]);
    assert.ok(matchesAnyTag(tags, "docker kubernetes terraform"));
    assert.ok(matchesAnyTag(tags, "kubernetes terraform docker"));
  });

  it("handles empty tag set (never matches)", () => {
    const tags = new Set();
    assert.equal(matchesAnyTag(tags, "python"), false);
    assert.equal(matchesAnyTag(tags, ""), false);
  });
});