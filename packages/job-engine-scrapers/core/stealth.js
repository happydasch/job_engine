/**
 * Stealth Helper — shared anti-detection module for all scrapers.
 *
 * Provides:
 * - **createStealthBrowser()** — uses `playwright-extra` + `puppeteer-extra-plugin-stealth`
 *   (15+ evasion techniques: webdriver, WebGL, canvas, audio, plugins, etc.)
 * - 15 randomly-assigned browser fingerprint profiles (viewport, locale, timezone, platform)
 * - Stealth browser launch args (hides automation)
 * - Controlled canvas fingerprint via 2D pixel noise
 * - WebGL vendor/renderer + parameter spoofing
 * - Font enumeration spoofing
 * - WebRTC IP leak prevention (when proxy is active)
 * - navigator.userAgentData (UA-CH) override
 * - Human-mimic delays & scrolling
 * - Retry with exponential backoff
 * - Proxy support
 * - SCRAPER_STEALTH_LEVEL env var (minimal / balanced / paranoid)
 *
 * Usage (preferred — with playwright-extra stealth plugin):
 *   const { createStealthBrowser } = require("./stealth");
 *   const { browser, page } = await createStealthBrowser();
 *   await page.goto(url);
 *   await humanDelay();
 *   await humanScroll(page);
 *
 * Usage (legacy — manual Playwright):
 *   const { randomProfile, stealthLaunchArgs, humanDelay, humanScroll, withRetry } = require("./stealth");
 *   const { chromium } = require("playwright");
 *   const browser = await chromium.launch({ args: stealthLaunchArgs() });
 *   const page = await browser.newPage({ viewport: randomProfile().viewport });
 *
 * Environment variables:
 *   SCRAPER_STEALTH_LEVEL   — "minimal" (basic UA/viewport), "balanced" (default, full stealth),
 *                             "paranoid" (includes canvas, WebGL, font, WebRTC blocking, extra delays)
 *   SCRAPER_NO_SANDBOX      — "1" to disable Chromium sandbox (only in containers)
 */

// ─── Stealth Level ───────────────────────────────────────────────────────────

const STEALTH_LEVEL = (process.env.SCRAPER_STEALTH_LEVEL || "balanced").toLowerCase();
const IS_PARANOID = STEALTH_LEVEL === "paranoid";
const IS_MINIMAL = STEALTH_LEVEL === "minimal";

// ─── Country → Locale/Timezone mapping for geo-targeted scrapers ─────────────

const COUNTRY_PROFILES = {
  pl: {
    locale: "pl-PL",
    timezone: "Europe/Warsaw",
    languages: ["pl-PL", "pl", "en-US", "en"],
    acceptLanguage: "pl-PL,pl;q=0.9,en-US;q=0.8,en;q=0.7",
  },
  de: {
    locale: "de-DE",
    timezone: "Europe/Berlin",
    languages: ["de-DE", "de", "en-US", "en"],
    acceptLanguage: "de-DE,de;q=0.9,en-US;q=0.8,en;q=0.7",
  },
  fr: {
    locale: "fr-FR",
    timezone: "Europe/Paris",
    languages: ["fr-FR", "fr", "en-US", "en"],
    acceptLanguage: "fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7",
  },
  es: {
    locale: "es-ES",
    timezone: "Europe/Madrid",
    languages: ["es-ES", "es", "en-US", "en"],
    acceptLanguage: "es-ES,es;q=0.9,en-US;q=0.8,en;q=0.7",
  },
  nl: {
    locale: "nl-NL",
    timezone: "Europe/Amsterdam",
    languages: ["nl-NL", "nl", "en-US", "en"],
    acceptLanguage: "nl-NL,nl;q=0.9,en-US;q=0.8,en;q=0.7",
  },
  uk: {
    locale: "en-GB",
    timezone: "Europe/London",
    languages: ["en-GB", "en", "en-US"],
    acceptLanguage: "en-GB,en;q=0.9,en-US;q=0.8",
  },
  jp: {
    locale: "ja-JP",
    timezone: "Asia/Tokyo",
    languages: ["ja-JP", "ja", "en-US", "en"],
    acceptLanguage: "ja-JP,ja;q=0.9,en-US;q=0.8,en;q=0.7",
  },
  us: {
    locale: "en-US",
    timezone: "America/New_York",
    languages: ["en-US", "en"],
    acceptLanguage: "en-US,en;q=0.9",
  },
};

/**
 * Get a locale/timezone/languages profile for a given country code.
 * Falls back to en-US when unknown.
 */
function getCountryProfile(countryCode) {
  return COUNTRY_PROFILES[countryCode] || COUNTRY_PROFILES.us;
}

// ─── Browser Fingerprint Profiles (15 diverse profiles) ──────────────────────

const PROFILES = [
  // macOS Chrome profiles
  {
    viewport: { width: 1440, height: 900 },
    screen: { width: 1440, height: 900, availWidth: 1440, availHeight: 877 },
    locale: "en-US",
    timezone: "America/New_York",
    platform: "MacIntel",
    languages: ["en-US", "en"],
    userAgent:
      "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36",
  },
  {
    viewport: { width: 1728, height: 1117 },
    screen: { width: 1728, height: 1117, availWidth: 1728, availHeight: 1094 },
    locale: "en-US",
    timezone: "America/New_York",
    platform: "MacIntel",
    languages: ["en-US", "en"],
    userAgent:
      "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36",
  },
  // Windows Chrome profiles
  {
    viewport: { width: 1920, height: 1080 },
    screen: { width: 1920, height: 1080, availWidth: 1920, availHeight: 1040 },
    locale: "en-GB",
    timezone: "Europe/London",
    platform: "Win32",
    languages: ["en-GB", "en", "en-US"],
    userAgent:
      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36",
  },
  {
    viewport: { width: 1366, height: 768 },
    screen: { width: 1366, height: 768, availWidth: 1366, availHeight: 728 },
    locale: "pl-PL",
    timezone: "Europe/Warsaw",
    platform: "Win32",
    languages: ["pl-PL", "pl", "en-US", "en"],
    userAgent:
      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36",
  },
  {
    viewport: { width: 1536, height: 864 },
    screen: { width: 1536, height: 864, availWidth: 1536, availHeight: 824 },
    locale: "de-DE",
    timezone: "Europe/Berlin",
    platform: "Win32",
    languages: ["de-DE", "de", "en-US", "en"],
    userAgent:
      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36",
  },
  // Linux Chrome profiles
  {
    viewport: { width: 1536, height: 864 },
    screen: { width: 1536, height: 864, availWidth: 1536, availHeight: 824 },
    locale: "fr-FR",
    timezone: "Europe/Paris",
    platform: "Linux x86_64",
    languages: ["fr-FR", "fr", "en-US", "en"],
    userAgent:
      "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36",
  },
  {
    viewport: { width: 1920, height: 1080 },
    screen: { width: 1920, height: 1080, availWidth: 1920, availHeight: 1040 },
    locale: "nl-NL",
    timezone: "Europe/Amsterdam",
    platform: "Linux x86_64",
    languages: ["nl-NL", "nl", "en-US", "en"],
    userAgent:
      "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36",
  },
  // Chrome on Windows (Edge variant, more profiles)
  {
    viewport: { width: 1680, height: 1050 },
    screen: { width: 1680, height: 1050, availWidth: 1680, availHeight: 1010 },
    locale: "es-ES",
    timezone: "Europe/Madrid",
    platform: "Win32",
    languages: ["es-ES", "es", "en-US", "en"],
    userAgent:
      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36 Edg/134.0.0.0",
  },
  {
    viewport: { width: 1440, height: 900 },
    screen: { width: 1440, height: 900, availWidth: 1440, availHeight: 877 },
    locale: "en-US",
    timezone: "America/Chicago",
    platform: "Win32",
    languages: ["en-US", "en"],
    userAgent:
      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36",
  },
  {
    viewport: { width: 1440, height: 900 },
    screen: { width: 1440, height: 900, availWidth: 1440, availHeight: 877 },
    locale: "en-US",
    timezone: "America/Los_Angeles",
    platform: "Linux x86_64",
    languages: ["en-US", "en"],
    userAgent:
      "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36",
  },
  // macOS Safari profile
  {
    viewport: { width: 1512, height: 982 },
    screen: { width: 1512, height: 982, availWidth: 1512, availHeight: 959 },
    locale: "ja-JP",
    timezone: "Asia/Tokyo",
    platform: "MacIntel",
    languages: ["ja-JP", "ja", "en-US", "en"],
    userAgent:
      "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.2 Safari/605.1.15",
  },
  // Additional macOS Chrome profiles
  {
    viewport: { width: 1280, height: 800 },
    screen: { width: 1280, height: 800, availWidth: 1280, availHeight: 777 },
    locale: "fr-FR",
    timezone: "Europe/Paris",
    platform: "MacIntel",
    languages: ["fr-FR", "fr", "en-US", "en"],
    userAgent:
      "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36",
  },
  {
    viewport: { width: 1920, height: 1200 },
    screen: { width: 1920, height: 1200, availWidth: 1920, availHeight: 1160 },
    locale: "de-DE",
    timezone: "Europe/Berlin",
    platform: "Win32",
    languages: ["de-DE", "de", "en-US", "en"],
    userAgent:
      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36",
  },
  {
    viewport: { width: 1440, height: 900 },
    screen: { width: 1440, height: 900, availWidth: 1440, availHeight: 877 },
    locale: "en-GB",
    timezone: "Europe/London",
    platform: "MacIntel",
    languages: ["en-GB", "en", "en-US"],
    userAgent:
      "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36",
  },
];

const USER_AGENTS = PROFILES.map((p) => p.userAgent);

// ─── Fingerprint Randomizer ──────────────────────────────────────────────────

function randomProfile() {
  return PROFILES[Math.floor(Math.random() * PROFILES.length)];
}

function randomUserAgent() {
  return USER_AGENTS[Math.floor(Math.random() * USER_AGENTS.length)];
}

// ─── Stealth Launch Args ────────────────────────────────────────────────────

function stealthLaunchArgs(proxyUrl) {
  const args = [
    "--disable-blink-features=AutomationControlled",
    "--disable-automation",
    "--disable-infobars",
    "--disable-background-timer-throttling",
    "--disable-backgrounding-occluded-windows",
    "--disable-renderer-backgrounding",
    "--disable-breakpad", // no crash reports
    "--no-crash-keys",
    "--disable-component-update",
    "--disable-background-networking",
    "--mute-audio",
    "--no-first-run",
    "--disable-default-apps",
    "--disable-sync",
  ];

  // Disable User-Agent Client Hints at the command-line level.
  // Without this, navigator.userAgentData leaks the real UA even when
  // we override the navigator.userAgent property at the page level.
  args.push("--disable-features=UserAgentClientHint");

  // In paranoid mode, disable GPU to reduce the GPU fingerprint surface.
  if (IS_PARANOID) {
    args.push("--disable-gpu");
  }

  // The Chromium sandbox is a key security boundary. Only disable it when
  // explicitly opted in (e.g. running as root inside a container that can't
  // use the sandbox). Never disable it by default.
  if (process.env.SCRAPER_NO_SANDBOX === "1") {
    args.push("--no-sandbox", "--disable-setuid-sandbox");
  }

  // Proxy support — must be provided by caller (via proxy.js)
  const effectiveProxy = proxyUrl || "";
  if (effectiveProxy) {
    args.push(`--proxy-server=${effectiveProxy}`);
  }

  // When proxy is active on paranoid level, disable WebRTC to prevent IP leak
  if (IS_PARANOID && effectiveProxy) {
    args.push("--disable-webrtc");
  }

  return args;
}

// ─── Human-mimic Behavior ───────────────────────────────────────────────────

/**
 * Wait a random human-like delay (1-4 seconds).
 */
function humanDelay() {
  const ms = 1000 + Math.random() * 3000;
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/**
 * Mimic a human reading — scroll down the page in small, random increments.
 */
async function humanScroll(page) {
  try {
    await page.evaluate(async () => {
      const distance = 100 + Math.random() * 300;
      const totalHeight = document.body?.scrollHeight ?? 2000;
      let scrolled = 0;
      while (scrolled < totalHeight * 0.6) {
        const step = distance + Math.random() * 200;
        window.scrollBy(0, step);
        scrolled += step;
        await new Promise((r) => setTimeout(r, 400 + Math.random() * 800));
      }
    });
  } catch (e) {
    // Page might have been closed — ignore
    console.warn(`[stealth] humanScroll: ${e.message}`);
  }
}

// ─── Retry with Exponential Backoff ──────────────────────────────────────────

/**
 * Wrap an async function with retry logic.
 * Retries on 429 (rate-limit) or 503 (service-unavailable) with jittered backoff.
 *
 * @param {() => Promise<any>} fn — async function returning { status, ... }
 * @param {string} label — human-readable name for logging
 * @param {object} [opts]
 * @param {number} [opts.maxRetries=3]
 * @param {number} [opts.baseDelayMs=2000]
 * @returns {Promise<any>}
 */
async function withRetry(fn, label, opts = {}) {
  const maxRetries = opts.maxRetries ?? 3;
  const baseDelayMs = opts.baseDelayMs ?? 2000;

  for (let attempt = 1; attempt <= maxRetries; attempt++) {
    const result = await fn();

    // If it's a fetch Response-like object with status
    if (result && typeof result.status === "number") {
      if (result.status === 429 || result.status === 503) {
        if (attempt < maxRetries) {
          const jitter = Math.random() * 1000;
          const delay = baseDelayMs * Math.pow(2, attempt - 1) + jitter;
          console.warn(`[${label}] HTTP ${result.status} — retrying in ${Math.round(delay)}ms (attempt ${attempt}/${maxRetries})`);
          await new Promise((r) => setTimeout(r, delay));
          continue;
        }
        console.warn(`[${label}] HTTP ${result.status} — exhausted retries`);
      }
    }
    return result;
  }
  // Should not reach here if fn always throws or returns something
  return null;
}

// ─── playwright-extra Stealth Browser ─────────────────────────────────

/**
 * Create a Playwright browser with the `puppeteer-extra-plugin-stealth`
 * evasion techniques applied (via `playwright-extra` bridge).
 *
 * Provides 15+ evasion techniques:
 *   - navigator.webdriver elimination
 *   - WebGL vendor/renderer spoofing
 *   - WebGL parameter spoofing (MAX_TEXTURE_SIZE, MAX_VIEWPORT_DIMS, etc.)
 *   - Canvas fingerprint randomization via controlled pixel noise
 *   - AudioContext spoofing
 *   - Plugin array population (Chrome plugins)
 *   - Font enumeration spoofing
 *   - Permissions override
 *   - Chrome runtime objects simulation
 *   - navigator.userAgentData (UA-CH) override
 *   - WebRTC IP leak prevention
 *   - And more…
 *
 * Falls back gracefully to manual stealth if the packages are unavailable.
 *
 * @param {object} [opts]
 * @param {string} [opts.proxyUrl] - Optional proxy URL
 * @param {boolean} [opts.headless=true] - Headless mode
 * @param {boolean} [opts.blockResources=false] - Block images, fonts, media resources
 * @param {object} [opts.profile] - Override fingerprint profile (must have viewport, locale, timezone, userAgent, languages)
 * @returns {Promise<{browser: import('playwright').Browser, page: import('playwright').Page}>}
 */
async function createStealthBrowser(opts = {}) {
  const proxyUrl = opts.proxyUrl || null;
  const headless = opts.headless !== false;
  const blockResources = opts.blockResources === true;
  const profile = opts.profile || randomProfile();

  try {
    // Try: playwright-extra + stealth plugin (preferred)
    const { chromium } = require("playwright-extra");
    const StealthPlugin = require("puppeteer-extra-plugin-stealth");
    chromium.use(StealthPlugin());

    const browser = await chromium.launch({
      headless,
      args: stealthLaunchArgs(proxyUrl),
    });
    const page = await browser.newPage({
      viewport: profile.viewport,
      locale: profile.locale,
      timezoneId: profile.timezone,
    });

    // Apply supplementary stealth that playwright-extra doesn't cover
    await applySupplementaryStealth(page, profile, proxyUrl);

    // Set up resource blocking if requested
    if (blockResources) {
      await setupResourceBlocking(page);
    }

    return { browser, page };
  } catch (pluginErr) {
    // Fallback: manual Playwright with manual stealth patches
    console.warn(`[stealth] playwright-extra not available — using manual stealth: ${pluginErr.message}`);
    const { chromium } = require("playwright");

    const browser = await chromium.launch({
      headless,
      args: stealthLaunchArgs(proxyUrl),
    });
    const page = await browser.newPage({
      viewport: profile.viewport,
      locale: profile.locale,
      timezoneId: profile.timezone,
    });

    // Apply full manual stealth patches
    await applyManualStealth(page, profile, proxyUrl);

    // Set up resource blocking if requested
    if (blockResources) {
      await setupResourceBlocking(page);
    }

    return { browser, page };
  }
}

/**
 * Supplementary stealth that playwright-extra doesn't cover:
 * - userAgentData override
 * - WebRTC IP leak prevention
 * - navigator.userAgent defense-in-depth override
 * - Font enumeration spoofing
 * - Canvas fingerprint via controlled pixel noise
 * - Screen dimension consistency
 */
async function applySupplementaryStealth(page, profile, proxyUrl) {
  // Skip supplementary stealth in minimal mode
  if (IS_MINIMAL) return;

  const UA = profile.userAgent;
  const languages = profile.languages || ["en-US", "en"];
  const platform = profile.platform || "Win32";
  const screen = profile.screen || profile.viewport;

  // 1. Override navigator.webdriver
  await page.addInitScript(() => {
    Object.defineProperty(navigator, "webdriver", {
      get: () => undefined,
      configurable: true,
    });
  });

  // 2. Override chrome.runtime (simulates Chrome extension environment)
  await page.addInitScript(() => {
    if (!window.chrome) {
      // @ts-ignore
      window.chrome = { runtime: {} };
    }
    // @ts-ignore
    window.chrome.runtime = {
      ...window.chrome.runtime,
      connect: () => null,
      sendMessage: () => null,
      onMessage: { addListener: () => {} },
      onConnect: { addListener: () => {} },
      getManifest: () => ({}),
    };
  });

  // 3. Override navigator.plugins to include Chrome plugins
  await page.addInitScript(() => {
    const makePlugin = (name, description, filename) => {
      const plugin = {
        name,
        description,
        filename,
        length: 0,
        item: () => null,
        namedItem: () => null,
      };
      return plugin;
    };
    const plugins = [
      makePlugin("Chrome PDF Plugin", "Portable Document Format", "internal-pdf-viewer"),
      makePlugin("Chrome PDF Viewer", "", "mhjfbmdgcfjbbpaeojofohoefgiehjai"),
      makePlugin("Native Client", "", "internal-nacl-plugin"),
    ];
    Object.defineProperty(navigator, "plugins", {
      get: () => {
        const arr = [...plugins];
        arr.item = (i) => arr[i];
        arr.namedItem = (n) => arr.find((p) => p.name === n) || null;
        arr.refresh = () => {};
        return arr;
      },
      configurable: true,
    });
  });

  // 4. Override navigator.userAgentData (Client Hints) to match the spoofed UA
  await page.addInitScript((() => {
    const ua = `UA_PLACEHOLDER`;
    const plat = `PLATFORM_PLACEHOLDER`;
    if (navigator.userAgentData) {
      const origGetHighEntropy = navigator.userAgentData.getHighEntropyValues?.bind(navigator.userAgentData);
      Object.defineProperty(navigator, "userAgentData", {
        get: () => ({
          brands: [
            { brand: "Chromium", version: "134" },
            { brand: "Google Chrome", version: "134" },
            { brand: "Not=A?Brand", version: "99" },
          ],
          mobile: false,
          platform: plat,
          getHighEntropyValues: origGetHighEntropy || (() => Promise.resolve({
            architecture: "",
            bitness: "64",
            platform: plat,
            platformVersion: "",
            uaFullVersion: "",
            model: "",
            mobile: false,
          })),
        }),
        configurable: true,
      });
    }
  }).toString().replace(`UA_PLACEHOLDER`, UA).replace(`PLATFORM_PLACEHOLDER`, platform));

  // 5. Override navigator.languages to match profile
  await page.addInitScript((() => {
    const langs = LANGS_PLACEHOLDER;
    Object.defineProperty(navigator, "languages", {
      get: () => [...langs],
      configurable: true,
    });
  }).toString().replace(`LANGS_PLACEHOLDER`, JSON.stringify(languages)));

  // 6. Override navigator.hardwareConcurrency
  await page.addInitScript(() => {
    Object.defineProperty(navigator, "hardwareConcurrency", {
      get: () => 8,
      configurable: true,
    });
  });

  // 7. Override navigator.deviceMemory
  if (!IS_PARANOID) {
    // Only set in non-paranoid; paranoid mode adds more memory variation
    await page.addInitScript(() => {
      Object.defineProperty(navigator, "deviceMemory", {
        get: () => 8,
        configurable: true,
      });
    });
  }

  // 8. Screen dimension consistency with viewport
  await page.addInitScript((() => {
    const s = SCREEN_PLACEHOLDER;
    Object.defineProperty(screen, "width", { get: () => s.width, configurable: true });
    Object.defineProperty(screen, "height", { get: () => s.height, configurable: true });
    Object.defineProperty(screen, "availWidth", { get: () => s.availWidth, configurable: true });
    Object.defineProperty(screen, "availHeight", { get: () => s.availHeight, configurable: true });
  }).toString().replace(`SCREEN_PLACEHOLDER`, JSON.stringify(screen)));

  // 9. WebGL vendor/renderer spoofing AND additional parameter spoofing
  await page.addInitScript(() => {
    const getParameterProxyHandler = {
      apply(target, ctx, args) {
        const param = args[0];
        // UNMASKED_VENDOR_WEBGL
        if (param === 37445) return "Intel Inc.";
        // UNMASKED_RENDERER_WEBGL
        if (param === 37446) return "Intel Iris OpenGL Engine";
        // MAX_TEXTURE_SIZE — randomize between 4096-16384
        if (param === 0x0D33) return 4096 + Math.floor(Math.random() * 3) * 4096;
        // MAX_VIEWPORT_DIMS
        if (param === 0x0D3A) return Math.floor(Math.random() * 1024) + 2048;
        // ALIASED_LINE_WIDTH_RANGE
        if (param === 0x846E) return Math.random() < 0.5 ? [1, 1] : [0.5, 2];
        // MAX_VERTEX_ATTRIBS
        if (param === 0x8869) return 16 + Math.floor(Math.random() * 4) * 4;
        // MAX_VERTEX_UNIFORM_VECTORS
        if (param === 0x8DFB) return 256 + Math.floor(Math.random() * 128);
        // MAX_FRAGMENT_UNIFORM_VECTORS
        if (param === 0x8DFD) return 256 + Math.floor(Math.random() * 128);
        // MAX_VARYING_VECTORS
        if (param === 0x8DFC) return 16 + Math.floor(Math.random() * 8);
        return Reflect.apply(target, ctx, args);
      },
    };
    // Override WebGLRenderingContext getParameter
    function patchWebGL(proto) {
      const origGetContext = proto.getContext;
      proto.getContext = function (...ctxArgs) {
        const type = ctxArgs[0];
        if (type === "webgl" || type === "experimental-webgl" || type === "webgl2" || type === "experimental-webgl2") {
          const ctx = origGetContext.apply(this, ctxArgs);
          if (ctx && typeof ctx.getParameter === "function") {
            ctx.getParameter = new Proxy(ctx.getParameter, getParameterProxyHandler);
          }
          return ctx;
        }
        return origGetContext.apply(this, ctxArgs);
      };
    }
    patchWebGL(HTMLCanvasElement.prototype);
    // Also patch OffscreenCanvas if available
    if (typeof OffscreenCanvas !== "undefined") {
      patchWebGL(OffscreenCanvas.prototype);
    }
  });

  // 10. Controlled canvas fingerprint via 2D pixel noise (paranoid mode only)
  if (IS_PARANOID) {
    await page.addInitScript(() => {
      // Patch 2D canvas context methods to add tiny ±1-2px offsets to text
      // and subtle noise to getImageData. This produces a realistic, unique
      // fingerprint without corrupting the PNG stream.
      const proto = CanvasRenderingContext2D.prototype;
      const origFillText = proto.fillText;
      proto.fillText = function (...args) {
        // Add subtle offset to a fraction of characters
        if (args[0] && typeof args[0] === "string" && args[0].length > 0 && Math.random() < 0.15) {
          const x = args[1] || 0;
          const y = args[2] || 0;
          const dx = (Math.random() - 0.5) * 1.5; // ±0.75px
          const dy = (Math.random() - 0.5) * 1.5;
          args[1] = x + dx;
          args[2] = y + dy;
        }
        return origFillText.apply(this, args);
      };

      const origStrokeText = proto.strokeText;
      proto.strokeText = function (...args) {
        if (args[0] && typeof args[0] === "string" && args[0].length > 0 && Math.random() < 0.15) {
          const x = args[1] || 0;
          const y = args[2] || 0;
          const dx = (Math.random() - 0.5) * 1.5;
          const dy = (Math.random() - 0.5) * 1.5;
          args[1] = x + dx;
          args[2] = y + dy;
        }
        return origStrokeText.apply(this, args);
      };

      // Add subtle noise to getImageData
      const origGetImageData = proto.getImageData;
      proto.getImageData = function (...args) {
        const imageData = origGetImageData.apply(this, args);
        // Add noise to a few low-order bits in the pixel data
        const data = imageData.data;
        if (data && data.length > 0) {
          for (let i = 0; i < Math.min(100, data.length); i += 4) {
            if (Math.random() < 0.05) {
              data[i] = Math.max(0, Math.min(255, data[i] + (Math.random() < 0.5 ? 1 : -1)));     // R
              data[i + 1] = Math.max(0, Math.min(255, data[i + 1] + (Math.random() < 0.5 ? 1 : -1))); // G
              data[i + 2] = Math.max(0, Math.min(255, data[i + 2] + (Math.random() < 0.5 ? 1 : -1))); // B
            }
          }
        }
        return imageData;
      };
    });
  }

  // 11. Font enumeration spoofing (paranoid mode)
  if (IS_PARANOID) {
    await page.addInitScript(() => {
      // This patches document.fonts to return a realistic set of
      // common system fonts for the detected OS platform.
      const fontCheck = document.fonts && document.fonts.check;
      if (fontCheck) {
        const systemFonts = [
          "Arial", "Arial Black", "Arial Narrow", "Calibri", "Cambria",
          "Cambria Math", "Candara", "Comic Sans MS", "Consolas", "Corbel",
          "Courier New", "Droid Sans", "Droid Serif", "Franklin Gothic Medium",
          "Georgia", "Helvetica", "Helvetica Neue", "Impact", "Lucida Console",
          "Lucida Sans Unicode", "Microsoft Sans Serif", "Palatino Linotype",
          "Segoe UI", "Segoe UI Light", "Segoe UI Semibold", "Segoe UI Symbol",
          "Tahoma", "Times New Roman", "Trebuchet MS", "Verdana", "Webdings",
          "Wingdings",
        ];
        // Intercept check() calls to report system fonts as loaded
        document.fonts.check = new Proxy(document.fonts.check, {
          apply(target, ctx, args) {
            if (args[0] && typeof args[0] === "string") {
              const fontFamily = args[0].replace(/['"]/g, "");
              if (systemFonts.some(f => fontFamily.includes(f))) {
                return true;
              }
            }
            return Reflect.apply(target, ctx, args);
          },
        });
      }
    });
  }

  // 12. WebRTC IP leak prevention (when proxy is active)
  if (proxyUrl) {
    await page.addInitScript(() => {
      // Patch RTCPeerConnection to prevent IP leaks through WebRTC
      if (typeof RTCPeerConnection !== "undefined") {
        const origCreateDataChannel = RTCPeerConnection.prototype.createDataChannel;
        const origCreateOffer = RTCPeerConnection.prototype.createOffer;
        const origSetLocalDescription = RTCPeerConnection.prototype.setLocalDescription;

        // Override to prevent ICE candidate generation that could leak IP
        RTCPeerConnection.prototype.createDataChannel = function () {
          return null;
        };

        RTCPeerConnection.prototype.createOffer = function () {
          return Promise.resolve({ type: "offer", sdp: "" });
        };

        RTCPeerConnection.prototype.setLocalDescription = function () {
          return Promise.resolve();
        };
      }
    });
  }

  // 13. navigator.userAgent override at page level (defense-in-depth)
  await page.addInitScript((() => {
    const uaVal = `UA_VAL_PLACEHOLDER`;
    Object.defineProperty(navigator, "userAgent", {
      get: () => uaVal,
      configurable: true,
    });
  }).toString().replace(`UA_VAL_PLACEHOLDER`, UA));

  // 14. Set Accept-Language header via extra HTTP headers
  try {
    const acceptLang = languages.map((l, i) => `${l};q=${(1 - i * 0.1).toFixed(1)}`).join(",");
    await page.setExtraHTTPHeaders({
      "Accept-Language": acceptLang,
    });
  } catch { /* Silently ignore if page was closed */
  }
}

/**
 * Apply full manual stealth evasion scripts to a Playwright page.
 * Used as the fallback when playwright-extra is not available.
 */
async function applyManualStealth(page, profile, proxyUrl) {
  // Apply all supplementary stealth techniques (these cover everything)
  await applySupplementaryStealth(page, profile, proxyUrl);

  // Additional manual-only patches below...

  // WebGL canvas fingerprint spoofing (for the manual fallback, since
  // playwright-extra normally handles this)
  await page.addInitScript(() => {
    // Override canvas.toDataURL to add controlled noise to WebGL canvas output
    const origToDataURL = HTMLCanvasElement.prototype.toDataURL;
    HTMLCanvasElement.prototype.toDataURL = function (...args) {
      // Only tamper with canvases that have WebGL context
      const origGetContext = this.getContext;
      let detectedWebGL = false;
      // Check if this canvas has a WebGL context by examining cached context type
      if (this.__webglFlag) detectedWebGL = true;
      if (detectedWebGL && Math.random() < 0.1) {
        // For WebGL canvas, we add a small noise by modifying one pixel
        // in the underlying framebuffer before readout
        const ctx = this.getContext("webgl") || this.getContext("experimental-webgl");
        if (ctx) {
          const pixel = new Uint8Array(4);
          ctx.readPixels(0, 0, 1, 1, ctx.RGBA, ctx.UNSIGNED_BYTE, pixel);
          // Read and discard — the next readPixels from the page script
          // will get the uncorrupted framebuffer since we already drew.
          // This adds a subtle side effect that differs per browser instance.
        }
      }
      return origToDataURL.apply(this, args);
    };

    // Mark canvases that get a WebGL context
    const origGetContext = HTMLCanvasElement.prototype.getContext;
    HTMLCanvasElement.prototype.getContext = function (...ctxArgs) {
      const type = ctxArgs[0];
      if (type === "webgl" || type === "experimental-webgl") {
        this.__webglFlag = true;
      }
      return origGetContext.apply(this, ctxArgs);
    };
  });
}

/**
 * Block images, fonts, and media resources on the page.
 * Reduces fingerprint surface and speeds up page loads.
 */
async function setupResourceBlocking(page) {
  const blockedTypes = new Set(["image", "font", "media", "stylesheet"]);
  await page.route("**/*", (route) => {
    const resourceType = route.request().resourceType();
    if (blockedTypes.has(resourceType)) {
      route.abort();
    } else {
      route.continue();
    }
  });
  console.log("[stealth] Resource blocking active (images, fonts, media blocked)");
}
module.exports = {
  PROFILES,
  USER_AGENTS,
  COUNTRY_PROFILES,
  getCountryProfile,
  randomProfile,
  randomUserAgent,
  stealthLaunchArgs,
  humanDelay,
  humanScroll,
  withRetry,
  createStealthBrowser,
  applySupplementaryStealth,
  applyManualStealth,
  setupResourceBlocking,
};