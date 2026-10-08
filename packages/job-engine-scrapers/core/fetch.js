#!/usr/bin/env node
/**
 * Shared Fetch Utilities — fetchWithRetry(), checkWaf(), fetchHtml(), fetchJson().
 *
 * Consolidates the ~15-line fetch + error handling + WAF check + retry pattern
 * that is duplicated in every fetch-based scraper.
 *
 * All fetch-based scrapers automatically use proxy rotation via proxy.js.
 * Browser scrapers configure proxy separately through createStealthBrowser().
 *
 * Usage:
 *   const { fetchHtml, fetchJson, checkWaf } = require("./core/fetch");
 *   const html = await fetchHtml(url, "[MyScraper]");
 *   const data = await fetchJson(url, { headers }, "[MyScraper]");
 */

const stealth = require("./stealth");
const proxy = require("./proxy");
const createLogger = require("./logger");

const log = createLogger("fetch");

const DEFAULT_UA =
  "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36";

/** Default connection timeout in milliseconds */
const DEFAULT_TIMEOUT_MS = 15000;

// ─── Proxy integration (dynamic rotation for fetch-based scrapers) ────────────

/** @type {import('undici').ProxyAgent|null} */
let _proxyAgent = null;
/** @type {boolean} */
let _proxyInitialized = false;

/**
 * Detect whether global-agent is already routing native fetch() (HTTP_PROXY set).
 * When active, we must NOT also use undici ProxyAgent (avoid double-proxying).
 * @returns {boolean}
 */
function _globalAgentActive() {
  try {
    return !!(global.GLOBAL_AGENT && global.GLOBAL_AGENT.HTTP_PROXY);
  } catch (e) {
    log.warn(`_globalAgentActive check failed: ${e.message}`);
    return false;
  }
}

/**
 * Lazily initialise a ProxyAgent from proxy.js (once per scraper run).
 * Returns null when:
 *  - global-agent is already active (HTTP_PROXY/HTTPS_PROXY static env var)
 *  - proxy.js returns no available proxy
 *
 * @returns {Promise<import('undici').ProxyAgent|null>}
 */
async function _getProxyAgent() {
  if (_proxyInitialized) return _proxyAgent;
  _proxyInitialized = true;

  // When HTTP_PROXY env var is set, global-agent handles it — skip undici Agent.
  if (_globalAgentActive()) {
    log.info("global-agent active — native fetch() already proxied; skipping undici ProxyAgent");
    return null;
  }

  const proxyUrl = await proxy.getRandomProxyUrl();
  if (!proxyUrl) {
    log.info("No proxy available — fetch() will connect directly");
    return null;
  }

  try {
    const { ProxyAgent } = require("undici");
    _proxyAgent = new ProxyAgent(proxyUrl);
    log.info(`Using proxy via undici: ${proxyUrl.replace(/:(\d+)$/, ":*****")}`);
  } catch (err) {
    log.warn(`Failed to create ProxyAgent: ${err.message} — fetch will connect directly`);
  }
  return _proxyAgent;
}

/**
 * Build fetch options with proxy dispatcher attached when available.
 * Also adds a random User-Agent from stealth profiles each call.
 * @param {object} opts
 * @returns {Promise<object>}
 */
async function _buildFetchOpts(opts = {}) {
  const agent = await _getProxyAgent();
  const effectiveOpts = { ...opts };
  if (agent) {
    effectiveOpts.dispatcher = agent;
  }
  // Always use a random user agent from stealth profiles
  if (!effectiveOpts.headers) effectiveOpts.headers = {};
  if (!effectiveOpts.headers["User-Agent"]) {
    effectiveOpts.headers["User-Agent"] = stealth.randomUserAgent();
  }
  return effectiveOpts;
}

/**
 * Check response text for WAF/blocking indicators.
 *
 * @param {string} text — HTML body
 * @returns {boolean} — true if WAF detected
 */
function checkWaf(text) {
  // Match only challenge/interstitial markers, NOT any mention of Cloudflare.
  // Legit Cloudflare-fronted pages routinely reference `cdn-cgi/` asset URLs and
  // the word "Cloudflare" in footers/CSP — keying on those flagged good pages as
  // blocked and made fetchHtml discard them after pointless retries.
  if (!text || typeof text !== "string") return false;
  return (
    text.includes("Just a moment") ||
    text.includes("Attention Required! | Cloudflare") ||
    text.includes("Checking your browser before accessing") ||
    text.includes("challenge-platform") ||
    text.includes("cf-chl-")
  );
}

/**
 * Fetch a URL with error handling, returning { ok, status, body, error }.
 * Does NOT throw on non-ok status — returns { ok: false, status } instead.
 * Automatically routes through a dynamic proxy when available.
 *
 * @param {string} url
 * @param {object} [opts] — fetch options (headers, etc.)
 * @returns {Promise<{ok: boolean, status: number, body: string|null, error: string|null}>}
 */
async function fetchResult(url, opts = {}) {
  // User-Agent comes from _buildFetchOpts (stealth.randomUserAgent) unless caller overrides
  const headers = {
    Accept: "text/html,application/xhtml+xml",
    ...opts.headers,
  };
  // Create an AbortController for connection timeout
  const controller = new AbortController();
  const timeoutMs = opts.timeout || opts.timeoutMs || DEFAULT_TIMEOUT_MS;
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs);
  // Attach proxy dispatcher + random UA when available
  const fetchOpts = await _buildFetchOpts({ ...opts, headers, signal: controller.signal });
  try {
    const resp = await fetch(url, fetchOpts);
    clearTimeout(timeoutId);
    const body = await resp.text();
    return { ok: resp.ok, status: resp.status, body, error: null };
  } catch (err) {
    clearTimeout(timeoutId);
    if (err.name === "AbortError") {
      return { ok: false, status: 0, body: null, error: `Connection timed out after ${timeoutMs}ms` };
    }
    return { ok: false, status: 0, body: null, error: err.message };
  }
}

/**
 * Clear the cached proxy agent so the next call re-fetches from proxy.js.
 * This enables proxy rotation on request failure.
 */
function _clearProxyAgent() {
  _proxyAgent = null;
  _proxyInitialized = false;
  proxy.clearCache();
}

/**
 * Fetch HTML from a URL, check for WAF, return text.
 * Throws on failure or WAF detection after exhausting all retries.
 * Retries on WAF block or HTTP 429/503 with proxy rotation and exponential backoff.
 *
 * @param {string} url
 * @param {string} label — for logging prefix, e.g. "[MyScraper]"
 * @param {object} [opts] — additional fetch options
 * @param {number} [opts.maxRetries=2] — how many times to retry with a fresh proxy
 * @returns {Promise<string>}
 * @throws {Error} when all retries are exhausted
 */
async function fetchHtml(url, label, opts = {}) {
  const maxRetries = opts.maxRetries ?? 2;
  let lastError = null;

  for (let attempt = 1; attempt <= maxRetries + 1; attempt++) {
    // Rotate to a fresh proxy ONLY on an actual retry. Clearing on attempt 1
    // (the common single-shot path) threw away the cached proxy list and forced
    // a full proxy-list re-download on every single request.
    if (attempt > 1) await _clearProxyAgent();
    const result = await fetchResult(url, opts);

    if (result.ok && result.body && !checkWaf(result.body)) {
      return result.body;
    }

    // Determine the reason
    if (result.ok && checkWaf(result.body)) {
      lastError = "WAF block";
      log.warn(`${label} WAF blocked (attempt ${attempt}/${maxRetries + 1})`);
    } else if (result.status === 429 || result.status === 503) {
      lastError = `HTTP ${result.status}`;
      log.warn(`${label} ${result.status} rate-limit/service-unavailable (attempt ${attempt}/${maxRetries + 1})`);
    } else if (!result.ok) {
      lastError = result.error || `HTTP ${result.status}`;
      log.warn(`${label} ${lastError} (attempt ${attempt}/${maxRetries + 1})`);
    }

    if (attempt <= maxRetries) {
      // Exponential backoff with jitter
      const delayMs = 2000 * Math.pow(2, attempt - 1) + Math.random() * 1000;
      log.info(`${label} Retrying after ${Math.round(delayMs)}ms with fresh proxy...`);
      await delay(delayMs);
    }
  }

  log.warn(`${label} Failed after ${maxRetries + 1} attempts: ${lastError}`);
  throw new Error(`${label} Failed after ${maxRetries + 1} attempts: ${lastError}`);
}

/**
 * Fetch JSON from a URL with retry support.
 * Automatically rotates proxy on retry via withRetry.
 *
 * @param {string} url
 * @param {object} [opts] — fetch options ({ headers, … })
 * @param {string} label — logging prefix
 * @param {number} [opts.maxRetries=2] — retry attempts with proxy rotation
 * @returns {Promise<object>} — parsed JSON
 * @throws {Error} when all retries are exhausted
 */
async function fetchJson(url, opts = {}, label = "") {
  const headers = { Accept: "application/json", ...opts.headers };
  const maxRetries = opts.maxRetries ?? 2;
  let lastError = null;

  for (let attempt = 1; attempt <= maxRetries + 1; attempt++) {
    // Fresh proxy + random UA only on an actual retry (see fetchHtml note).
    if (attempt > 1) await _clearProxyAgent();
    const controller = new AbortController();
    const timeoutMs = opts.timeout || opts.timeoutMs || DEFAULT_TIMEOUT_MS;
    const timeoutId = setTimeout(() => controller.abort(), timeoutMs);
    const fetchOpts = await _buildFetchOpts({ ...opts, headers, signal: controller.signal });

    try {
      const resp = await fetch(url, fetchOpts);
      clearTimeout(timeoutId);

      if (!resp.ok) {
        lastError = `HTTP ${resp.status}`;
        if ((resp.status === 429 || resp.status === 503) && attempt <= maxRetries) {
          log.warn(`${label} ${resp.status} — retry ${attempt}/${maxRetries + 1} with fresh proxy`);
          const delayMs = 2000 * Math.pow(2, attempt - 1) + Math.random() * 1000;
          await delay(delayMs);
          continue;
        }
        log.warn(`${label} API returned ${resp.status}`);
        throw new Error(`${label} API returned ${resp.status}`);
      }

      const data = await resp.json();
      return data;
    } catch (err) {
      clearTimeout(timeoutId);
      lastError = err.message;
      if (err.name === "AbortError") {
        lastError = `Connection timed out after ${timeoutMs}ms`;
      }
      if (attempt <= maxRetries) {
        log.warn(`${label} ${lastError} — retry ${attempt}/${maxRetries + 1} with fresh proxy`);
        const delayMs = 2000 * Math.pow(2, attempt - 1) + Math.random() * 1000;
        await delay(delayMs);
        continue;
      }
      log.warn(`${label} Network error: ${lastError}`);
      throw new Error(`${label} Network error: ${lastError}`);
    }
  }
  throw new Error(`${label} Failed after all retries: ${lastError}`);
}

/**
 * Simple delay helper.
 * @param {number} ms
 */
function delay(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

module.exports = { fetchHtml, fetchJson, fetchResult, checkWaf, delay, DEFAULT_UA };