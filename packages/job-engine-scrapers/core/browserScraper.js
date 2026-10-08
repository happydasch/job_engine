#!/usr/bin/env node
/**
 * BrowserScraper — shared base class for browser-based scrapers.
 *
 * Provides:
 * - Stealth browser launch with proxy, fingerprint rotation, resource blocking
 * - Per-navigation fingerprint rotation
 * - Human-mimic behavior (delays, scrolling, mouse movements)
 * - WAF detection and retry with different fingerprint profiles
 * - Screenshot capture on failure
 * - Resource blocking (images, fonts, media)
 * - Graceful browser lifecycle management
 *
 * Usage:
 *   const BrowserScraper = require("@job-engine-scrapers/core").browserScraper;
 *
 *   class MyScraper extends BrowserScraper {
 *     get id() { return "myscraper"; }
 *     get platform() { return "myscraper.com"; }
 *     async extractJobs(page) { /* ... *\/ }
 *   }
 *
 *   const scraper = new MyScraper({ maxPages: 3, headless: true });
 *   const jobs = await scraper.scrape();
 *
 * Environment variables inherited:
 *   SCRAPER_STEALTH_LEVEL — "minimal", "balanced" (default), or "paranoid"
 *   SCRAPER_NO_SANDBOX   — "1" to disable Chromium sandbox
 */

const { createStealthBrowser, randomProfile, humanDelay, humanScroll, setupResourceBlocking } = require("./stealth");
const proxy = require("./proxy");
const log = require("./logger")("browserScraper");

class BrowserScraper {
  /**
   * @param {object} [opts]
   * @param {number} [opts.maxPages=1] — max pages to scrape
   * @param {boolean} [opts.headless=true] — headless mode
   * @param {boolean} [opts.proxyEnabled=true] — enable proxy
   * @param {boolean} [opts.blockResources=false] — block images, fonts, media
   * @param {boolean} [opts.humanBehavior=true] — mimic human interaction
   * @param {number} [opts.requestDelayMs=2000] — base delay between requests
   * @param {string} [opts.country] — country code for locale matching (e.g. "pl", "de")
   */
  constructor(opts = {}) {
    this.maxPages = opts.maxPages || 1;
    this.headless = opts.headless !== false;
    this.proxyEnabled = opts.proxyEnabled !== false;
    this.blockResources = opts.blockResources === true;
    this.humanBehavior = opts.humanBehavior !== false;
    this.requestDelayMs = opts.requestDelayMs || 2000;
    this.country = opts.country || null;

    /** @type {import('playwright').Browser | null} */
    this.browser = null;
    /** @type {import('playwright').Page | null} */
    this.page = null;
    /** @type {string | null} */
    this._proxyUrl = null;
    /** @type {object} */
    this._profile = null;
  }

  /**
   * Subclass must return the scraper ID (e.g. "indeed").
   * @returns {string}
   */
  get id() {
    throw new Error("BrowserScraper subclass must implement get id()");
  }

  /**
   * Subclass must return the platform domain (e.g. "indeed.com").
   * @returns {string}
   */
  get platform() {
    throw new Error("BrowserScraper subclass must implement get platform()");
  }

  /**
   * Extract jobs from the current page. Subclass must implement.
   * @param {import('playwright').Page} page
   * @param {string} tag — search tag/keyword
   * @param {number} pageNum — current page number (1-based)
   * @returns {Promise<Array<object>>}
   */
  async extractJobs(page, tag, pageNum) {
    throw new Error("BrowserScraper subclass must implement extractJobs(page, tag, pageNum)");
  }

  /**
   * Optional hook called after browser launch but before any navigation.
   * Override to set up cookies, headers, or other page-level configuration.
   * @returns {Promise<void>}
   */
  async onLaunch() {
    // No-op by default; override in subclasses
  }

  /**
   * Optional: build the URL for a given tag and page.
   * @param {string} tag
   * @param {number} pageNum
   * @returns {string}
   */
  buildUrl(tag, pageNum) {
    throw new Error("BrowserScraper subclass must implement buildUrl(tag, pageNum) or override navigateToPage()");
  }

  /**
   * Navigate to a page with WAF detection and retry.
   * Override this to customize navigation behavior per scraper.
   * @param {import('playwright').Page} page
   * @param {string} url
   * @returns {Promise<boolean>} — true if navigation succeeded without blocking
   */
  async navigateToPage(page, url) {
    try {
      await page.goto(url, { waitUntil: "domcontentloaded", timeout: 30000 });
    } catch (err) {
      log.warn(`[${this.id}] Navigation to ${url} failed: ${err.message}`);
      return false;
    }

    // Check for WAF/blocking
    const blocked = await this.detectWaf(page);
    if (blocked) {
      log.warn(`[${this.id}] WAF/blocking detected at ${url}`);
      if (this.debug) {
        await page.screenshot({ path: `/tmp/${this.id}_blocked.png`, fullPage: false }).catch(err => log.warn('Screenshot failed', err));
      }
      return false;
    }

    return true;
  }

  /**
   * Detect WAF/challenge pages. Override for site-specific detection.
   * @param {import('playwright').Page} page
   * @returns {Promise<boolean>}
   */
  async detectWaf(page) {
    try {
      return await page.evaluate(() => {
        const title = (document.title || "").toLowerCase();
        const body = (document.body?.innerText || document.body?.textContent || "").toLowerCase();

        // Title of an actual interstitial (localised variants included).
        const titleBlocked =
          title.includes("just a moment") ||
          title.includes("un momento") ||
          title.includes("attention required") ||
          title.includes("security check") ||
          title.includes("verifying you are human") ||
          /^\s*(403|forbidden)\b/.test(title);

        // Body copy that only appears on a live challenge page.
        const bodyBlocked =
          body.includes("verify you are human") ||
          body.includes("checking your browser before accessing") ||
          body.includes("needs to review the security of your connection") ||
          body.includes("enable javascript and cookies to continue");

        // The challenge widget rendered in the DOM. NB: `cdn-cgi/challenge-platform`
        // asset URLs and the word "cloudflare" appear on ordinary Cloudflare-fronted
        // pages, so keying on those flagged healthy pages as blocked — match the
        // interactive widget instead, and only when the page has almost no content.
        const hasChallengeWidget = !!document.querySelector(
          "#challenge-form, #cf-chl-widget, .cf-turnstile, iframe[src*='challenges.cloudflare.com'], #px-captcha, #recaptcha"
        );
        const widgetBlocked = hasChallengeWidget && body.length < 2000;

        // Cloudflare's interstitial script config — present on every challenge page
        // regardless of locale ("Un instant…", "Einen Moment…"), absent on real pages.
        const cfChallenge = typeof window._cf_chl_opt !== "undefined";

        return titleBlocked || bodyBlocked || widgetBlocked || cfChallenge;
      });
    } catch { /* Page evaluate failed — treat as not blocked */
      return false;
    }
  }

  /**
   * Rotate fingerprint profile for the next navigation.
   * Selects a new profile and applies it to the current page.
   */
  async rotateFingerprint() {
    this._profile = randomProfile();
    if (this.page) {
      try {
        await this.page.setViewportSize(this._profile.viewport);
      } catch { /* Page may be closed during rotation */ }
    }
    log.info(`[${this.id}] Rotated fingerprint: ${this._profile.locale} / ${this._profile.userAgent.slice(0, 60)}...`);
  }

  /**
   * Get the current search tags for this scraper.
   * Override to customize tag selection.
   * @returns {string[]}
   */
  getSearchTags() {
    const config = require("./config");
    return config.getSearchTerms();
  }

  /**
   * Get per-scraper config from scraper_config.yaml.
   */
  getScraperConfig() {
    const config = require("./config");
    return config.getScraper(this.id) || {};
  }

  /**
   * Optional hook called after browser launch and page creation.
   * Override in subclass for post-launch setup (e.g., cookie injection).
   * @returns {Promise<void>}
   */
  async onLaunch() {
    // No-op by default
  }

  /**
   * Launch the browser and set up the page with stealth.
   */
  async launch() {
    const proxyUrl = this.proxyEnabled ? await proxy.getRandomProxyUrl() : null;
    this._proxyUrl = proxyUrl;
    this._profile = randomProfile();

    const { browser, page } = await createStealthBrowser({
      proxyUrl,
      headless: this.headless,
      blockResources: this.blockResources,
      profile: this._profile,
    });

    this.browser = browser;
    this.page = page;

    log.info(`[${this.id}] Browser launched (proxy: ${proxyUrl ? "yes" : "no"}, headless: ${this.headless}, blockResources: ${this.blockResources})`);
    // Call onLaunch hook for subclass setup
    await this.onLaunch();
    return { browser, page };
  }

  /**
   * Close the browser.
   */
  async close() {
    if (this.browser) {
      try {
        await this.browser.close();
      } catch (err) {
        log.warn(`[${this.id}] Error closing browser: ${err.message}`);
      }
      this.browser = null;
      this.page = null;
    }
  }

  /**
   * Apply human-mimic behavior (delays + scrolling).
   */
  async applyHumanBehavior() {
    if (!this.humanBehavior) return;
    await humanDelay();
    if (this.page) {
      await humanScroll(this.page);
    }
    await humanDelay();
  }

  /**
   * Perform random mouse movements on the page.
   * @param {import('playwright').Page} page
   */
  async randomMouseMoves(page) {
    if (!this.humanBehavior) return;
    try {
      const viewport = page.viewportSize() || { width: 800, height: 600 };
      for (let i = 0; i < 3 + Math.floor(Math.random() * 3); i++) {
        const x = Math.random() * viewport.width;
        const y = Math.random() * viewport.height;
        await page.mouse.move(x, y);
        await new Promise((r) => setTimeout(r, 50 + Math.random() * 150));
      }
    } catch { /* Page may be closed during mouse moves */ }
  }

  /**
   * Main scrape orchestration method.
   * 1. Launches browser
   * 2. For each tag + page, navigates, extracts, applies human behavior
   * 3. Closes browser
   *
   * @returns {Promise<{platform: string, count: number, jobs: Array<object>}>}
   */
  async scrape() {
    const allJobs = new Map();
    let pagesLoaded = 0;
    let pagesBlocked = 0;
    const tags = this.getSearchTags();
    const cfg = this.getScraperConfig();
    const maxPages = cfg.max_pages || this.maxPages;
    this.debug = cfg.debug || process.env[`${this.id.toUpperCase()}_DEBUG`] === "1";

    try {
      await this.launch();
      if (!this.page) {
        log.error(`[${this.id}] Failed to launch browser`);
        return { platform: this.platform, count: 0, jobs: [] };
      }

      // Run optional subclass hook after launch
      await this.onLaunch();

      for (const tag of tags) {
        for (let p = 1; p <= maxPages; p++) {
          // Rotate fingerprint per page for better anti-detection
          if (p > 1) {
            await this.rotateFingerprint();
          }

          // Add random mouse movement before navigation
          await this.randomMouseMoves(this.page);

          // Build URL and navigate
          const url = this.buildUrl(tag, p);
          log.info(`[${this.id}] Searching "${tag}" page ${p}/${maxPages}`);

          const ok = await this.navigateToPage(this.page, url);
          if (!ok) {
            pagesBlocked++;
            log.info(`[${this.id}] Navigation failed/blocked on page ${p} — stopping`);
            break;
          }
          pagesLoaded++;

          // Apply human behavior
          await this.applyHumanBehavior();

          // Extract jobs
          let rawJobs = [];
          try {
            rawJobs = await this.extractJobs(this.page, tag, p);
          } catch (err) {
            log.warn(`[${this.id}] Extract error on page ${p}: ${err.message}`);
            if (this.debug) {
              await this.page.screenshot({ path: `/tmp/${this.id}_error_p${p}.png`, fullPage: false }).catch(err => log.warn('Screenshot failed', err));
            }
            break;
          }

          if (rawJobs.length === 0) {
            log.info(`[${this.id}] No jobs on page ${p} — stopping`);
            break;
          }

          // Process and deduplicate
          for (const job of rawJobs) {
            if (job.external_id && !allJobs.has(job.external_id)) {
              allJobs.set(job.external_id, job);
            }
          }
        }
      }
    } catch (err) {
      log.error(`[${this.id}] Fatal scrape error: ${err.message}`);
    } finally {
      await this.close();
    }

    // Every navigation blocked → the run produced nothing trustworthy. Fail loudly
    // so the runner records an error instead of a misleading "OK, 0 jobs".
    if (pagesLoaded === 0 && pagesBlocked > 0) {
      throw new Error(`[${this.id}] All ${pagesBlocked} page loads were blocked (WAF/login wall/HTTP error)`);
    }

    const jobs = [...allJobs.values()];
    log.info(`[${this.id}] ${jobs.length} matching offers`);
    return { platform: this.platform, count: jobs.length, jobs };
  }
}

module.exports = BrowserScraper;