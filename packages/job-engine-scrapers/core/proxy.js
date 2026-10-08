/**
 * Dynamic Proxy Rotation Helper for scrapers.
 *
 * Fetches proxy lists from configured sources, caches them with a TTL, and
 * returns a random proxy per caller. Falls back to a static env-var proxy, and
 * to a DIRECT connection (null) when nothing is configured — it never hard-fails
 * a run just because no proxy is available.
 *
 * Provides proxy health checking to filter out dead proxies, and browser launch
 * args that prevent WebRTC IP leaks when a proxy is active.
 *
 * ⚠ SECURITY: A proxy can read and tamper with every request/response routed
 * through it. The default source is a list of anonymous "free" public proxies,
 * which are UNTRUSTED — never route authenticated requests (e.g. anything using
 * LINKEDIN_COOKIE or other credentials) through them, since a hostile proxy can
 * steal or inject those. Fine for anonymous public-page scraping; for anything
 * sensitive set HTTP_PROXY / PROXY_SOURCES to a proxy you trust.
 *
 * Usage:
 *   const proxy = require("./proxy.js");
 *   const url = await proxy.getRandomProxyUrl();  // "http://ip:port" or null
 *   const args = proxy.getBrowserLaunchArgs(url); // WebRTC args for Playwright
 *
 * Environment variables:
 *   HTTP_PROXY / HTTPS_PROXY — Static proxy. If set, dynamic fetching is skipped.
 *   PROXY_SOURCES            — Comma-separated proxy-list URLs (ip:port per line).
 *                             Defaults to a public free-proxy list.
 *   PROXY_REFRESH_INTERVAL   — How often to re-fetch the list (ms, default 300000).
 *   PROXY_HEALTH_CHECK_URL   — URL to test proxy health against (default: http://ip-api.com/json).
 *                             Set empty to disable health checks.
 *   PROXY_HEALTH_CHECK_TIMEOUT — Timeout per health check in ms (default: 5000).
 */

// ─── Config ───────────────────────────────────────────────────────────────

// Default to a DIRECT connection (no proxy). The old default routed every
// request through anonymous free public proxies, which are ~99% dead/hostile —
// that produced timeouts, junk responses, and empty scrapes far more often than
// it evaded any block. Opt in explicitly via PROXY_SOURCES / HTTP_PROXY when a
// proxy is actually needed. Example free list (UNTRUSTED, see security note):
//   PROXY_SOURCES=https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/http.txt
const DEFAULT_SOURCES = [];

const REFRESH_INTERVAL = parseInt(process.env.PROXY_REFRESH_INTERVAL || "300000", 10);
const SOURCES = process.env.PROXY_SOURCES
  ? process.env.PROXY_SOURCES.split(",").map((s) => s.trim()).filter(Boolean)
  : DEFAULT_SOURCES;

const STATIC_PROXY = process.env.HTTPS_PROXY || process.env.HTTP_PROXY || null;

// ─── Cache state ────────────────────────────────────────────────────────────

/** @type {string[] | null} */
let cachedList = null;
/** @type {number} */
let lastFetch = 0;
/** @type {Promise<void> | null} */
let pendingFetch = null;

// ─── Static env-var proxy (also routes native fetch()) ──────────────────────

if (STATIC_PROXY) {
  console.log(`[proxy] Static proxy from env: ${STATIC_PROXY.replace(/\/\/.*@/, "//***@")}`);
  try {
    require("global-agent/bootstrap");
    global.GLOBAL_AGENT.HTTP_PROXY = STATIC_PROXY;
    console.log("[proxy] Routing native fetch() via global-agent");
  } catch { /* Optional dependency, ignore if unavailable */
    console.warn(
      "[proxy] Could not configure native fetch() proxying automatically.\n" +
        "[proxy] Install global-agent if HTTP_PROXY must also apply to fetch()-based scrapers."
    );
  }
}

// ─── Proxy health check ────────────────────────────────────────────────────────

const HEALTH_CHECK_URL = process.env.PROXY_HEALTH_CHECK_URL !== ""
  ? (process.env.PROXY_HEALTH_CHECK_URL || "http://ip-api.com/json")
  : null;
const HEALTH_CHECK_TIMEOUT = parseInt(process.env.PROXY_HEALTH_CHECK_TIMEOUT || "5000", 10);

/**
 * Test whether a proxy URL is working by fetching a known endpoint through it.
 * Uses the native fetch() with a tunnel-agent-like approach through the proxy.
 *
 * @param {string} proxyUrl — full proxy URL like "http://ip:port"
 * @returns {Promise<boolean>} — true if the proxy responds within timeout
 */
async function checkProxyHealth(proxyUrl) {
  if (!HEALTH_CHECK_URL) return true; // Health checks disabled
  if (!proxyUrl) return true; // Direct connection — always healthy

  try {
    // Use Node.js http module to make a request through the proxy
    const urlObj = new URL(proxyUrl);
    const targetUrl = new URL(HEALTH_CHECK_URL);
    const isHttps = targetUrl.protocol === "https:";

    const http = isHttps ? require("https") : require("http");
    const net = require("net");

    return new Promise((resolve) => {
      const timeout = setTimeout(() => {
        console.warn(`[proxy] Health check timed out for ${proxyUrl.replace(/:\d+$/, ":*****")}`);
        resolve(false);
      }, HEALTH_CHECK_TIMEOUT);

      try {
        // Connect to the proxy and issue a CONNECT or plain request
        const client = net.connect(urlObj.port || 80, urlObj.hostname, () => {
          const path = isHttps
            ? `${targetUrl.hostname}:${targetUrl.port || 443}`
            : `${targetUrl.pathname}${targetUrl.search}`;

          const request = isHttps
            ? `CONNECT ${path} HTTP/1.1\r\nHost: ${path}\r\n\r\n`
            : `GET ${path} HTTP/1.1\r\nHost: ${targetUrl.hostname}\r\nProxy-Connection: Keep-Alive\r\n\r\n`;

          client.write(request);
        });

        let responseData = "";
        client.on("data", (data) => {
          responseData += data.toString();
          // For CONNECT, we just need the 200 response
          if (responseData.includes("HTTP/1.1 200") || responseData.includes("HTTP/1.0 200")) {
            clearTimeout(timeout);
            client.destroy();
            resolve(true);
          }
        });

        client.on("error", () => {
          clearTimeout(timeout);
          resolve(false);
        });

        client.on("close", () => {
          clearTimeout(timeout);
          // If we got a response (even non-200), the proxy is alive
          resolve(responseData.length > 0);
        });
      } catch { /* Proxy unreachable, report as unhealthy */
        clearTimeout(timeout);
        resolve(false);
      }
    });
  } catch { /* Proxy unreachable, report as unhealthy */
    return false;
  }
}

/**
 * Get browser launch arguments to prevent WebRTC IP leaks when a proxy is active.
 *
 * @param {string|null} proxyUrl — proxy URL or null for direct connection
 * @returns {string[]} — array of Chromium launch args
 */
function getBrowserLaunchArgs(proxyUrl) {
  const args = [];
  if (proxyUrl) {
    args.push(`--proxy-server=${proxyUrl}`);
    // Prevent WebRTC from leaking the real IP — use mDNS to hide local IPs
    args.push("--enable-features=WebRTC-HideLocalIpsWithMdns");
    // Force proxy for all protocol types
    args.push("--proxy-bypass-list=<-loopback>");
  }
  return args;
}

// ─── Fetch & parse proxy list ───────────────────────────────────────────────

/**
 * Fetch proxy lists from configured sources and return parsed "ip:port" strings.
 *
 * @param {string[]} [sources]
 * @returns {Promise<string[]>}
 */
async function fetchProxyList(sources) {
  const urls = sources || SOURCES;
  const allProxies = new Set();

  for (const url of urls) {
    try {
      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), 10000);
      const resp = await fetch(url, { signal: controller.signal });
      clearTimeout(timeout);

      if (!resp.ok) {
        console.warn(`[proxy] Source returned ${resp.status}: ${url}`);
        continue;
      }

      const text = await resp.text();
      const lines = text.split("\n").map((l) => l.trim()).filter(Boolean);
      for (const line of lines) {
        if (/^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}:\d{2,5}$/.test(line)) {
          allProxies.add(line);
        }
      }
      console.log(`[proxy] Parsed ${lines.length} lines, ${allProxies.size} valid proxies from ${url}`);
    } catch (err) {
      console.warn(`[proxy] Failed to fetch ${url}: ${err.message}`);
    }
  }

  return [...allProxies];
}

/**
 * Ensure the proxy cache is populated (fetch if stale or empty).
 */
async function ensureCache() {
  // Static proxy or no configured sources → nothing to fetch.
  if (STATIC_PROXY || SOURCES.length === 0) return;

  const now = Date.now();

  if (pendingFetch) {
    try { await pendingFetch; } catch { /* Connection already closed, nothing to clean up */ }
    return;
  }

  if (cachedList && cachedList.length > 0 && now - lastFetch < REFRESH_INTERVAL) {
    return;
  }

  pendingFetch = (async () => {
    try {
      const list = await fetchProxyList();
      if (list.length > 0) {
        cachedList = list;
        lastFetch = Date.now();
        console.log(`[proxy] Cached ${cachedList.length} proxies (refresh every ${Math.round(REFRESH_INTERVAL / 1000)}s)`);
      }
    } catch (err) {
      console.warn(`[proxy] Fetch failed: ${err.message}`);
    } finally {
      pendingFetch = null;
    }
  })();

  await pendingFetch;
}

/**
 * Get a random proxy URL ("http://ip:port"), the static env proxy, or null for
 * a direct connection. Never throws — a missing proxy means "go direct".
 *
 * @returns {Promise<string|null>}
 */
async function getRandomProxyUrl() {
  if (STATIC_PROXY) return STATIC_PROXY;

  await ensureCache();

  if (cachedList && cachedList.length > 0) {
    const entry = cachedList[Math.floor(Math.random() * cachedList.length)];
    const url = `http://${entry}`;
    console.log(`[proxy] Selected random proxy: ${url.replace(/:\d+$/, ":*****")}`);
    return url;
  }

  return null; // Direct connection.
}

/** Clear the cache so the next getRandomProxyUrl() re-fetches. */
function clearCache() {
  cachedList = null;
  lastFetch = 0;
  pendingFetch = null;
}

// ─── Background warm-up (only when sources are configured) ───────────────────

if (!STATIC_PROXY && SOURCES.length > 0) {
  ensureCache().catch((err) => console.warn(`[proxy] Background warm-up failed: ${err.message}`));
}

// ─── Exports ────────────────────────────────────────────────────────────────

module.exports = {
  fetchProxyList,
  getRandomProxyUrl,
  clearCache,
  checkProxyHealth,
  getBrowserLaunchArgs,
};
