#!/usr/bin/env node
/**
 * Tests for core/output.js — writeOutput, printTopJobs, printCountSummary.
 */

const assert = require("node:assert");
const path = require("path");
const fs = require("fs");
const os = require("os");
const { describe, it, beforeEach, afterEach } = require("node:test");

const { writeOutput, printTopJobs, printCountSummary } = require("../core/output");

describe("writeOutput", () => {
  let tmpDir;

  beforeEach(() => {
    tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "output-test-"));
  });

  afterEach(() => {
    fs.rmSync(tmpDir, { recursive: true, force: true });
  });

  it("writes jobs to a JSON file", () => {
    const jobs = [
      {
        external_id: "test_001",
        platform: "test",
        title: "Test Job",
        company: "TestCo",
        url: "https://example.com/job",
        salary_min: 1000,
        salary_max: 5000,
        currency: "USD",
        skills: ["python"],
        contract_type: "B2B",
        location: "Remote",
        remote: true,
        category: "python",
        experience_level: "senior",
        requirements: "",
        discovered_at: "2026-07-01T00:00:00Z",
      },
    ];

    const filePath = writeOutput("test_scraper", jobs, { outputDir: tmpDir });
    assert.ok(fs.existsSync(filePath));

    const loaded = JSON.parse(fs.readFileSync(filePath, "utf-8"));
    assert.equal(loaded.length, 1);
    assert.equal(loaded[0].title, "Test Job");
  });

  it("filters out invalid jobs (missing required fields)", () => {
    const jobs = [
      {
        external_id: "valid_001",
        platform: "test",
        title: "Valid Job",
        company: "TestCo",
        url: "https://example.com/job/valid",
      },
      {
        // missing external_id
        platform: "test",
        title: "Invalid Job",
        company: "TestCo",
        url: "https://example.com/job/invalid",
      },
    ];

    const filePath = writeOutput("test_filter", jobs, { outputDir: tmpDir });
    const loaded = JSON.parse(fs.readFileSync(filePath, "utf-8"));
    assert.equal(loaded.length, 1);
    assert.equal(loaded[0].external_id, "valid_001");
  });

  it("sorts jobs by salary descending with currency normalization", () => {
    const jobs = [
      {
        external_id: "a",
        platform: "test", title: "Low", company: "C", url: "https://a",
        salary_max: 10000, currency: "USD", contract_type: "B2B",
        location: "Remote", remote: true, skills: [], category: "",
        experience_level: "", requirements: "", discovered_at: "",
      },
      {
        external_id: "b",
        platform: "test", title: "High", company: "C", url: "https://b",
        salary_max: 50000, currency: "USD", contract_type: "B2B",
        location: "Remote", remote: true, skills: [], category: "",
        experience_level: "", requirements: "", discovered_at: "",
      },
    ];

    const filePath = writeOutput("test_sort", jobs, { outputDir: tmpDir });
    const loaded = JSON.parse(fs.readFileSync(filePath, "utf-8"));
    assert.equal(loaded[0].title, "High");
    assert.equal(loaded[1].title, "Low");
  });

  it("handles empty jobs array", () => {
    const filePath = writeOutput("test_empty", [], { outputDir: tmpDir });
    assert.ok(fs.existsSync(filePath));
    const loaded = JSON.parse(fs.readFileSync(filePath, "utf-8"));
    assert.deepEqual(loaded, []);
  });
});

describe("printTopJobs", () => {
  it("prints nothing for empty array", () => {
    // Should not throw
    printTopJobs("[Test]", []);
  });

  it("prints top N jobs without throwing", () => {
    const jobs = [
      {
        title: "Test Job", company: "TestCo", salary_min: 1000, salary_max: 5000,
        currency: "USD", skills: ["python"], location: "Remote",
      },
    ];
    printTopJobs("[Test]", jobs, 5);
  });
});