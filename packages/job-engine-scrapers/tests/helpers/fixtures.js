#!/usr/bin/env node
/**
 * Shared test fixtures for scraper tests.
 *
 * Provides sample job data, mock config functions, and helper utilities.
 */

const path = require("path");
const fs = require("fs");
const os = require("os");

// ─── Sample job objects ─────────────────────────────────────────────────

const SAMPLE_JOB_FULL = {
  external_id: "test_full_001",
  platform: "justjoin.it",
  title: "Senior Python Developer",
  company: "TechCorp",
  url: "https://example.com/job/001",
  salary_min: 25000,
  salary_max: 40000,
  currency: "PLN",
  contract_type: "B2B",
  location: "Remote",
  remote: true,
  skills: ["python", "fastapi", "postgresql", "docker"],
  category: "python",
  experience_level: "senior",
  requirements: "Looking for an experienced Python developer...",
  discovered_at: "2026-07-01T10:00:00Z",
};

const SAMPLE_JOB_MINIMAL = {
  external_id: "test_min_001",
  platform: "testplatform",
  title: "Test Job",
  company: "TestCo",
  url: "https://example.com/job/min",
};

const SAMPLE_JOB_MISSING_REQUIRED = {
  // no external_id
  platform: "testplatform",
  title: "Broken Job",
  company: "BrokenCo",
  url: "https://example.com/job/broken",
};

const SAMPLE_JOB_NO_SALARY = {
  external_id: "test_nosal_001",
  platform: "testplatform",
  title: "No Salary Job",
  company: "NoPayCo",
  url: "https://example.com/job/nosal",
  salary_min: null,
  salary_max: null,
  currency: "USD",
  contract_type: "B2B",
  location: "Remote",
  remote: true,
  skills: [],
  category: "",
  experience_level: "",
  requirements: "",
  discovered_at: "2026-07-01T10:00:00Z",
};

const SAMPLE_JOBS = [SAMPLE_JOB_FULL, SAMPLE_JOB_MINIMAL, SAMPLE_JOB_NO_SALARY];

// ─── Mock config helpers ────────────────────────────────────────────────

/**
 * Temporarily override a module export by patching require.cache.
 * Returns a restore function.
 *
 * @param {string} modulePath - absolute path to the module
 * @param {object} mockExports - what require() should return
 * @returns {() => void} restore function
 */
function mockRequire(modulePath, mockExports) {
  const original = require.cache[modulePath];
  require.cache[modulePath] = {
    id: modulePath,
    filename: modulePath,
    loaded: true,
    exports: mockExports,
    paths: [],
    children: [],
  };
  return () => {
    delete require.cache[modulePath];
    if (original) {
      require.cache[modulePath] = original;
    }
  };
}

/**
 * Create a temporary YAML string file at a path, write content, return cleanup.
 * @param {string} filePath
 * @param {string} yamlContent
 * @returns {() => void}
 */
function createTempFile(filePath, content) {
  const dir = path.dirname(filePath);
  if (!fs.existsSync(dir)) {
    fs.mkdirSync(dir, { recursive: true });
  }
  fs.writeFileSync(filePath, content, "utf-8");
  return () => {
    try { fs.unlinkSync(filePath); } catch { /* File may not exist — cleanup best-effort */ }
  };
}

/**
 * Capture stdout / stderr output from a function call.
 * @param {Function} fn - async function to call
 * @returns {Promise<{ stdout: string, stderr: string }>}
 */
async function captureOutput(fn) {
  const chunks = { stdout: [], stderr: [] };
  const origLog = console.log;
  const origWarn = console.warn;
  const origErr = console.error;

  console.log = (...args) => chunks.stdout.push(args.join(" ") + "\n");
  console.warn = (...args) => chunks.stderr.push(args.join(" ") + "\n");
  console.error = (...args) => chunks.stderr.push(args.join(" ") + "\n");

  try {
    await fn();
  } finally {
    console.log = origLog;
    console.warn = origWarn;
    console.error = origErr;
  }
  return { stdout: chunks.stdout.join(""), stderr: chunks.stderr.join("") };
}

module.exports = {
  SAMPLE_JOB_FULL,
  SAMPLE_JOB_MINIMAL,
  SAMPLE_JOB_MISSING_REQUIRED,
  SAMPLE_JOB_NO_SALARY,
  SAMPLE_JOBS,
  mockRequire,
  createTempFile,
  captureOutput,
};
