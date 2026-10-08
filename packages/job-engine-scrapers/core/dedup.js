#!/usr/bin/env node
/**
 * Shared Dedup & Sort — deduplicateByKey(), sortBySalary().
 *
 * Consolidates the `new Map()` + `for` loop + sort pattern that is duplicated
 * in every scraper file's output section.
 *
 * Usage:
 *   const { deduplicateByKey, sortBySalary } = require("./core/dedup");
 *   const unique = deduplicateByKey(jobs, (j) => j.external_id);
 *   const sorted = sortBySalary(unique);
 */

const path = require("path");
const fs = require("fs");
const crypto = require("crypto");
const createLogger = require("./logger");

const log = createLogger("dedup");

// ──────────────────────────────────────────────────────────────────────────
// SeenJobsDB — persistent dedup state machine for scraper runs.
//
// Tracks seen job URLs in a JSON state file so that jobs discovered in one
// run can be skipped in subsequent runs.
//
// Status lifecycle:
//   new       — first time this URL was seen (default)
//   skipped   — deliberately skipped (e.g. low quality, excluded company)
//   evaluated — processed by the scoring/ranking pipeline
//   expired   — no longer valid (past TTL or removed by platform)
//
// Usage:
//   const { SeenJobsDB, deduplicateByKey, sortBySalary } = require("./core/dedup");
//   const db = new SeenJobsDB();
//   db.cleanup();  // expire old entries
//   const fresh = jobs.filter(j => db.isNew(j.url));
//   fresh.forEach(j => db.mark(j.url, "new"));
//   db.save();
// ──────────────────────────────────────────────────────────────────────────

const SEEN_JOBS_FILE = process.env.SEEN_JOBS_FILE
  || path.join(__dirname, "..", "..", "..", "data", "scraper-output", "seen_jobs.json");

const DEFAULT_TTL_DAYS = 30;

class SeenJobsDB {
  /**
   * @param {object} [opts]
   * @param {string} [opts.filePath] — path to the JSON state file
   * @param {number} [opts.ttlDays] — days before auto-expiry (default 30)
   */
  constructor(opts = {}) {
    this.filePath = opts.filePath || SEEN_JOBS_FILE;
    this.ttlMs = (opts.ttlDays || DEFAULT_TTL_DAYS) * 24 * 60 * 60 * 1000;
    /** @type {Record<string, { url: string, status: string, firstSeen: string, lastSeen: string }>} */
    this._data = {};
    this._dirty = false;
    this._load();
  }

  // ── Hashing ─────────────────────────────────────────────────────────

  /**
   * Return a deterministic hash for a URL string.
   * @param {string} url
   * @returns {string} hex SHA-256 (first 16 chars for compact storage)
   */
  _hash(url) {
    return crypto.createHash("sha256").update(url).digest("hex").slice(0, 16);
  }

  // ── Persistence ─────────────────────────────────────────────────────

  _load() {
    try {
      if (fs.existsSync(this.filePath)) {
        const raw = fs.readFileSync(this.filePath, "utf-8");
        this._data = JSON.parse(raw);
      }
    } catch (err) {
      log.warn(`Failed to load ${this.filePath}: ${err.message}`);
      this._data = {};
    }
  }

  /**
   * Persist to disk. Only writes if the data has changed since the last save.
   */
  save() {
    if (!this._dirty) return;
    const dir = path.dirname(this.filePath);
    if (!fs.existsSync(dir)) {
      fs.mkdirSync(dir, { recursive: true });
    }
    fs.writeFileSync(this.filePath, JSON.stringify(this._data, null, 2), "utf-8");
    this._dirty = false;
  }

  // ── Status helpers ──────────────────────────────────────────────────

  /**
   * Check whether a URL is new (not yet seen in any non-ignored status).
   * @param {string} url
   * @returns {boolean}
   */
  isNew(url) {
    const hash = this._hash(url);
    const entry = this._data[hash];
    if (!entry) return true;
    // Consider 'skipped' and 'expired' as re-scrape-able
    return entry.status === "skipped" || entry.status === "expired";
  }

  /**
   * Get the current status of a URL.
   * @param {string} url
   * @returns {string|null} — 'new', 'skipped', 'evaluated', 'expired', or null
   */
  getStatus(url) {
    const hash = this._hash(url);
    const entry = this._data[hash];
    return entry ? entry.status : null;
  }

  /**
   * Mark a URL with a status. Creates or updates the entry.
   * @param {string} url
   * @param {'new'|'skipped'|'evaluated'|'expired'} status
   */
  mark(url, status) {
    const hash = this._hash(url);
    const now = new Date().toISOString();
    if (this._data[hash]) {
      this._data[hash].status = status;
      this._data[hash].lastSeen = now;
    } else {
      this._data[hash] = { url, status, firstSeen: now, lastSeen: now };
    }
    this._dirty = true;
  }

  /**
   * Remove expired entries older than TTL.
   * Also cleans up 'expired' status entries that are past TTL.
   * @returns {number} — number of entries removed
   */
  cleanup() {
    const now = Date.now();
    const before = Object.keys(this._data).length;
    this._data = Object.fromEntries(
      Object.entries(this._data).filter(([, entry]) => {
        const age = now - new Date(entry.lastSeen).getTime();
        return age < this.ttlMs;
      }),
    );
    const removed = before - Object.keys(this._data).length;
    if (removed > 0) this._dirty = true;
    return removed;
  }

  /**
   * Return the count of entries with a given status.
   * @param {string} [status]
   * @returns {number}
   */
  count(status) {
    if (!status) return Object.keys(this._data).length;
    return Object.values(this._data).filter((e) => e.status === status).length;
  }
}

// ──────────────────────────────────────────────────────────────────────────
// Legacy dedup helpers
// ──────────────────────────────────────────────────────────────────────────

/**
 * Build a stable, collision-resistant id fragment from an arbitrary input
 * (usually a URL). Replaces the widespread `Buffer.from(url).toString("base64")
 * .slice(0, 16)` pattern, which truncated to ~12 URL bytes so URLs sharing a
 * leading prefix collided and were silently deduped away.
 *
 * @param {string} input
 * @returns {string} 16-char hex SHA-256 prefix
 */
function stableId(input) {
  return crypto.createHash("sha256").update(String(input ?? "")).digest("hex").slice(0, 16);
}

/**
 * Deduplicate an array of objects by a key function.
 */
function deduplicateByKey(items, keyFn) {
  const map = new Map();
  for (const item of items) {
    const key = keyFn(item);
    if (!map.has(key)) {
      map.set(key, item);
    }
  }
  return Array.from(map.values());
}

/**
 * Sort jobs by salary descending (highest first).
 * Jobs without salary are placed at the end.
 *
 * @param {object[]} jobs
 * @returns {object[]} — new sorted array
 */
function sortBySalary(jobs) {
  return [...jobs].sort((a, b) => (b.salary_max ?? 0) - (a.salary_max ?? 0));
}

module.exports = { SeenJobsDB, deduplicateByKey, sortBySalary, stableId };