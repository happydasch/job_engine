#!/usr/bin/env node
/**
 * Tests for core/dedup.js — deduplicateByKey, sortBySalary, stableId, SeenJobsDB.
 */

const assert = require("node:assert");
const path = require("path");
const fs = require("fs");
const os = require("os");
const { describe, it, beforeEach, afterEach } = require("node:test");

const { deduplicateByKey, sortBySalary, stableId, SeenJobsDB } = require("../core/dedup");

// ─── stableId ────────────────────────────────────────────────────────────

describe("stableId", () => {
  it("produces a 16-character hex string", () => {
    const id = stableId("https://example.com/job/123");
    assert.equal(id.length, 16);
    assert.ok(/^[0-9a-f]+$/.test(id));
  });

  it("is deterministic (same input → same output)", () => {
    const input = "https://example.com/job/123";
    assert.equal(stableId(input), stableId(input));
  });

  it("produces different hashes for different inputs", () => {
    assert.notEqual(
      stableId("https://example.com/job/a"),
      stableId("https://example.com/job/b")
    );
  });

  it("handles empty string", () => {
    const id = stableId("");
    assert.equal(id.length, 16);
  });

  it("handles null/undefined gracefully", () => {
    assert.equal(stableId(null).length, 16);
    assert.equal(stableId(undefined).length, 16);
  });
});

// ─── deduplicateByKey ───────────────────────────────────────────────────

describe("deduplicateByKey", () => {
  it("removes duplicates by key function", () => {
    const items = [
      { id: "a", val: 1 },
      { id: "b", val: 2 },
      { id: "a", val: 3 },
    ];
    const result = deduplicateByKey(items, (x) => x.id);
    assert.equal(result.length, 2);
    assert.equal(result[0].id, "a");
    assert.equal(result[0].val, 1); // first occurrence wins
    assert.equal(result[1].id, "b");
  });

  it("returns empty array for empty input", () => {
    assert.deepEqual(deduplicateByKey([], (x) => x), []);
  });

  it("preserves order of first occurrences", () => {
    const items = [
      { id: "z", val: 1 },
      { id: "a", val: 2 },
      { id: "z", val: 3 },
      { id: "b", val: 4 },
    ];
    const result = deduplicateByKey(items, (x) => x.id);
    assert.equal(result.length, 3);
    assert.equal(result[0].id, "z");
    assert.equal(result[1].id, "a");
    assert.equal(result[2].id, "b");
  });
});

// ─── sortBySalary ───────────────────────────────────────────────────────

describe("sortBySalary", () => {
  it("sorts jobs by salary_max descending", () => {
    const jobs = [
      { title: "Low", salary_max: 30000 },
      { title: "High", salary_max: 100000 },
      { title: "Medium", salary_max: 50000 },
    ];
    const sorted = sortBySalary(jobs);
    assert.equal(sorted[0].title, "High");
    assert.equal(sorted[1].title, "Medium");
    assert.equal(sorted[2].title, "Low");
  });

  it("places jobs without salary at the end", () => {
    const jobs = [
      { title: "No Salary", salary_max: null },
      { title: "Has Salary", salary_max: 50000 },
    ];
    const sorted = sortBySalary(jobs);
    assert.equal(sorted[0].title, "Has Salary");
    assert.equal(sorted[1].title, "No Salary");
  });

  it("does not mutate the original array", () => {
    const jobs = [
      { title: "B", salary_max: 30000 },
      { title: "A", salary_max: 100000 },
    ];
    const sorted = sortBySalary(jobs);
    assert.notEqual(sorted, jobs);
  });

  it("handles empty array", () => {
    assert.deepEqual(sortBySalary([]), []);
  });
});

// ─── SeenJobsDB ─────────────────────────────────────────────────────────

describe("SeenJobsDB", () => {
  let tmpDir;
  let dbPath;

  beforeEach(() => {
    tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "seenjobs-test-"));
    dbPath = path.join(tmpDir, "seen_jobs.json");
  });

  afterEach(() => {
    fs.rmSync(tmpDir, { recursive: true, force: true });
  });

  it("starts empty with new file path", () => {
    const db = new SeenJobsDB({ filePath: dbPath });
    assert.equal(db.count(), 0);
  });

  it("loads existing state from disk", () => {
    // Compute the correct hash for the test URL
    const crypto = require("crypto");
    const testHash = crypto.createHash("sha256").update("https://example.com/job/1").digest("hex").slice(0, 16);
    fs.writeFileSync(dbPath, JSON.stringify({
      [testHash]: {
        url: "https://example.com/job/1",
        status: "new",
        firstSeen: "2026-01-01T00:00:00Z",
        lastSeen: "2026-01-01T00:00:00Z",
      },
    }));
    const db = new SeenJobsDB({ filePath: dbPath });
    assert.equal(db.count(), 1);
    assert.equal(db.getStatus("https://example.com/job/1"), "new");
  });

  it("marks a URL as seen", () => {
    const db = new SeenJobsDB({ filePath: dbPath });
    db.mark("https://example.com/job/1", "new");
    assert.equal(db.isNew("https://example.com/job/1"), false);
  });

  it("returns true isNew for unseen URL", () => {
    const db = new SeenJobsDB({ filePath: dbPath });
    assert.ok(db.isNew("https://unseen.com/job/99"));
  });

  it("considers 'skipped' URLs as re-scrape-able", () => {
    const db = new SeenJobsDB({ filePath: dbPath });
    db.mark("https://example.com/job/skip", "skipped");
    assert.ok(db.isNew("https://example.com/job/skip"));
  });

  it("considers 'expired' URLs as re-scrape-able", () => {
    const db = new SeenJobsDB({ filePath: dbPath });
    db.mark("https://example.com/job/exp", "expired");
    assert.ok(db.isNew("https://example.com/job/exp"));
  });

  it("persists to disk on save()", () => {
    const db = new SeenJobsDB({ filePath: dbPath });
    db.mark("https://example.com/job/save-test", "evaluated");
    db.save();
    assert.ok(fs.existsSync(dbPath));
    const loaded = JSON.parse(fs.readFileSync(dbPath, "utf-8"));
    assert.ok(Object.keys(loaded).length > 0);
  });

  it("cleanup removes entries past TTL", () => {
    fs.writeFileSync(dbPath, JSON.stringify({
      oldentry: {
        url: "https://old.com/job",
        status: "new",
        firstSeen: "2020-01-01T00:00:00Z",
        lastSeen: "2020-01-01T00:00:00Z",
      },
    }));
    const db = new SeenJobsDB({ filePath: dbPath, ttlDays: 1 });
    const removed = db.cleanup();
    assert.ok(removed > 0);
    assert.equal(db.count(), 0);
  });

  it("count() with status filter works", () => {
    const db = new SeenJobsDB({ filePath: dbPath });
    db.mark("https://a.com/job1", "new");
    db.mark("https://a.com/job2", "evaluated");
    assert.equal(db.count("new"), 1);
    assert.equal(db.count("evaluated"), 1);
  });
});