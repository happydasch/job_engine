#!/usr/bin/env node
/**
 * Indeed Scraper — extends BrowserScraper for indeed.com.
 *
 * Searches Indeed for each search tag, extracts job listings from the
 * JavaScript-rendered DOM, and filters for matching tags.
 *
 * Features:
 *   - Country-aware subdomain selection (e.g. pl.indeed.com, de.indeed.com)
 *   - Locale/timezone/language matching via getCountryProfile()
 *   - Cloudflare/WAF detection with fingerprint rotation retry
 *   - INDEED_COOKIE support for bypassing Cloudflare
 *   - Resource blocking (images, fonts, media) for speed + stealth
 *
 * Environment variables:
 *   INDEED_COOKIE — optional JSON cookie array to bypass Cloudflare.
 *   INDEED_DEBUG  — set "1" to save screenshots on failure for debugging.
 */

const { getCountryProfile, humanDelay, humanScroll } = require("@job-engine-scrapers/core").stealth;
const { extractSkills } = require("@job-engine-scrapers/core").skills;
const { parseSalaryRange, parseHourlyRateToYearly, detectCurrency } = require("@job-engine-scrapers/core").salary;
const { writeOutput, printTopJobs, saveRawData } = require("@job-engine-scrapers/core").output;
const { stableId } = require("@job-engine-scrapers/core").dedup;
const { getTagSet, matchesAnyTag } = require("@job-engine-scrapers/core").tags;
const config = require("@job-engine-scrapers/core").config;
const BrowserScraper = require("@job-engine-scrapers/core").browserScraper;

const log = require("@job-engine-scrapers/core").logger("indeed");

const TAGS = config.getTags();
const TAG_SET = getTagSet();
const SCRAPER_CFG = config.getScraper("indeed");
const MAX_PAGES = SCRAPER_CFG ? SCRAPER_CFG.max_pages : 3;
const DEBUG = process.env.INDEED_DEBUG === "1";

// Country-aware Indeed domain mapping
const COUNTRY_DOMAINS = {
  pl: "pl.indeed.com",
  de: "de.indeed.com",
  uk: "uk.indeed.com",
  fr: "fr.indeed.com",
  es: "es.indeed.com",
  nl: "nl.indeed.com",
  it: "it.indeed.com",
  jp: "jp.indeed.com",
  au: "au.indeed.com",
  ca: "ca.indeed.com",
  in: "in.indeed.com",
  us: "www.indeed.com",
};

// ─── Indeed job card selectors (multi-level fallback) ───────────────────

// Level 1: Modern Indeed UI (circa 2024-2025)
const MODERN_CARD_SELECTORS = [
  '[data-testid="search-result"]',
  '[data-testid*="job-card"]',
  '[class*="job_seen_beacon"]',
  '[class*="JobCard"]',
  ".card",
];

// Level 2: Generic job card selectors (fallback)
const GENERIC_CARD_SELECTORS = [
  '[class*="job-card"]',
  '[class*="job-result"]',
  '[class*="JobSearch"]',
  "li[class*='job']",
];

// Combined card selectors
const CARD_SELECTORS = [...MODERN_CARD_SELECTORS, ...GENERIC_CARD_SELECTORS];

// Field selectors for job extraction (tried in order for each field)
const TITLE_SELECTORS = [
  '[data-testid="jobTitle"]',
  '[id^="jobTitle-"]',
  ".jobTitle",
  "h2",
  "h3",
  '[class*="title"]',
  '[class*="jobTitle"]',
  'a[class*="title"]',
];

const COMPANY_SELECTORS = [
  '[data-testid="company-name"]',
  '[data-testid="companyName"]',
  ".companyName",
  '[class*="company"]',
  '[class*="employer"]',
];

const LOCATION_SELECTORS = [
  '[data-testid="text-location"]',
  '[data-testid="location"]',
  ".location",
  '[class*="location"]',
];

const SALARY_SELECTORS = [
  '[data-testid="attribute_snippet"]',
  '[data-testid="estimated-salary"]',
  ".estimated-salary",
  '[class*="salary"]',
  '[class*="compensation"]',
  '[class*="metadata"]',
];

const LINK_SELECTORS = [
  'a[href*="/rc/clk"]',
  'a[href*="/company/"]',
  'a[class*="jcs-JobTitle"]',
  '[id^="jobTitle-"]',
  'a[href*="/job/"]',
];

/**
 * Query a single field from a card using multiple selectors (ordered).
 */
function queryField(card, selectors) {
  for (const sel of selectors) {
    const el = card.querySelector(sel);
    if (el) return el;
  }
  return null;
}

/**
 * Query all matching field texts from a card (e.g. salary may be in multiple places).
 */
function queryFieldText(card, selectors) {
  for (const sel of selectors) {
    const el = card.querySelector(sel);
    if (el && el.textContent) return el.textContent.trim();
  }
  return "";
}

class IndeedScraper extends BrowserScraper {
  constructor(opts = {}) {
    super(opts);
    this._currentTag = "";
    this._currentPageNum = 1;
    const country = this.country || (SCRAPER_CFG && SCRAPER_CFG.country) || "us";
    this._domain = COUNTRY_DOMAINS[country] || "www.indeed.com";
    this._countryProfile = getCountryProfile(country);
    log.info(`[indeed] Country: ${country}, Domain: ${this._domain}, Locale: ${this._countryProfile.locale}`);
  }

  get id() {
    return "indeed";
  }

  get platform() {
    return "indeed.com";
  }

  getSearchTags() {
    return TAGS;
  }

  buildUrl(tag, pageNum) {
    this._currentTag = tag;
    this._currentPageNum = pageNum;
    const baseUrl = `https://${this._domain}/jobs?q=${encodeURIComponent(tag)}`;
    return pageNum > 1 ? `${baseUrl}&start=${(pageNum - 1) * 10}` : baseUrl;
  }

  async onLaunch() {
    // Set Accept-Language header matching the country profile
    await this.page
      .setExtraHTTPHeaders({
        "Accept-Language": this._countryProfile.acceptLanguage,
      })
      .catch(() => {
        log.warn("Failed to set extra HTTP headers");
      });

    // Inject Indeed session cookie if provided via env var
    const cookieStr = process.env.INDEED_COOKIE;
    if (cookieStr) {
      try {
        let cookies;
        if (typeof cookieStr === "string" && (cookieStr.startsWith("[") || cookieStr.startsWith("{"))) {
          cookies = JSON.parse(cookieStr);
        }
        if (Array.isArray(cookies)) {
          await this.page
            .context()
            .addCookies(
              cookies.map((c) => ({
                name: c.name,
                value: c.value,
                domain: c.domain || `.${this._domain}`,
                path: c.path || "/",
              }))
            );
          log.info("Applied Indeed session cookies");
        }
      } catch (err) {
        log.info(`Could not parse INDEED_COOKIE — skipping: ${err.message}`);
      }
    }
  }

  async navigateToPage(page, url) {
    const tag = this._currentTag;
    const pageNum = this._currentPageNum;
    const legacyUrl = `https://${this._domain}/q-${encodeURIComponent(tag)}-jobs.html${pageNum > 1 ? `?start=${(pageNum - 1) * 10}` : ""}`;

    // Try the modern URL then the legacy path. NB: Cloudflare challenges rapid
    // sequential requests from a headless browser once the IP is flagged (see the
    // INDEED_COOKIE note in the header) — retrying/backing off per tag does not
    // beat a persistent block, it only slows the run, so we fail fast and let the
    // caller move on. Reliable multi-tag runs need a cf_clearance cookie or proxy.
    for (const attemptUrl of [url, legacyUrl]) {
      try {
        await page.goto(attemptUrl, { waitUntil: "domcontentloaded", timeout: 15000 });
        const blocked = await this.detectWaf(page);
        if (!blocked) return true;
        log.warn(`[${this.id}] WAF/blocking detected at ${attemptUrl}`);
      } catch (err) {
        log.info(`[${this.id}] Navigation to ${attemptUrl} failed: ${err.message}`);
      }
    }
    return false;
  }

  async extractJobs(page, tag, pageNum) {
    log.info(`Searching "${tag}" page ${pageNum}…`);

    // Wait for page to settle (short)
    await page.waitForTimeout(2000);

    // Check page info for blocking / content.
    // NOTE: selectors are passed IN as an argument — referencing the Node-side
    // CARD_SELECTORS const directly inside page.evaluate() throws a ReferenceError
    // in the browser context, which silently discarded the whole page probe.
    // innerText is layout-dependent and returns "" when stylesheets are blocked,
    // so fall back to textContent for the body-content heuristics.
    const pageInfo = await page
      .evaluate((cardSelectors) => {
        const title = document.title.toLowerCase();
        const body = ((document.body?.innerText || "") + " " + (document.body?.textContent || "")).toLowerCase();
        // Precise challenge detection — match the interstitial title/widget, NOT
        // the mere presence of Cloudflare (Indeed is Cloudflare-fronted, so
        // `cf-challenge`/`cloudflare` substrings appear on every healthy page).
        const hasChallengeWidget = !!document.querySelector(
          "#challenge-form, #cf-chl-widget, .cf-turnstile, iframe[src*='challenges.cloudflare.com']"
        );
        return {
          title,
          bodyPreview: body.slice(0, 500),
          blocked:
            title.includes("just a moment") ||
            title.includes("un momento") ||
            title.includes("attention required") ||
            title.includes("security check") ||
            title.includes("verifying you are human") ||
            body.includes("verify you are human") ||
            body.includes("checking your browser before accessing") ||
            (hasChallengeWidget && body.length < 2000),
          hasJobs: body.includes("jobs") || body.includes("hiring") || body.includes("salary") || body.includes("we found"),
          bodyLength: body.length,
          headingText: (document.querySelector("h1")?.textContent || "").slice(0, 200),
          selectorHits: cardSelectors.map((s) => ({
            sel: s,
            count: document.querySelectorAll(s).length,
          })),
        };
      }, CARD_SELECTORS)
      .catch(() => ({ blocked: false, hasJobs: false, bodyLength: 0, headingText: "", selectorHits: [], bodyPreview: "", title: "" }));

    if (pageInfo.blocked) {
      log.info(` Blocked by WAF/Cloudflare on page ${pageNum}`);
      log.info(`   Title: "${pageInfo.title}"`);
      log.info(`   H1: "${pageInfo.headingText}"`);

      if (DEBUG) {
        await page.screenshot({ path: `/tmp/indeed_blocked_p${pageNum}.png`, fullPage: false }).catch(() => {});
        log.info(`   Screenshot saved to /tmp/indeed_blocked_p${pageNum}.png`);
      }
      return [];
    }

    log.info(`Page title: "${pageInfo.title}"`);
    log.info(`Body text: ${pageInfo.bodyLength} chars`);

    if (DEBUG) {
      log.info(`Selector hits:`, pageInfo.selectorHits.filter((h) => h.count > 0));
    }

    // Wait for job cards using prioritized selectors.
    // The rendered DOM is the PRIMARY extraction source — it yields rich fields
    // (company, location, salary, snippet). Embedded JSON is only a fallback:
    // the bare data-jk anchors it can reach carry titles/links but no snippet,
    // so preferring it silently starved the tag filter and returned 0 results.
    let cardFound = false;
    let usedSelector = "";

    for (const sel of CARD_SELECTORS) {
      try {
        const count = await page.evaluate((s) => document.querySelectorAll(s).length, sel);
        if (count > 0) {
          await page.waitForSelector(sel, { timeout: 5000 }).catch(() => {
            log.warn(`Timeout waiting for selector "${sel}" — falling back`);
          });
          cardFound = true;
          usedSelector = `${sel} (${count})`;
          log.info(`Found ${count} cards via "${sel}"`);
          break;
        }
      } catch { /* Selector not found on page, continue */ }
    }

    if (!cardFound) {
      // Last resort: check if there's any meaningful content
      log.info(`No job cards found via selectors on page ${pageNum}`);
      log.info(`   Title: "${pageInfo.title}"`);
      log.info(`   Heading: "${pageInfo.headingText}"`);

      // Try a more aggressive DOM dump
      const domPreview = await page
        .evaluate(() => {
          const main = document.querySelector("main, #main, [role='main']");
          return {
            hasMain: !!main,
            mainText: main?.innerText?.slice(0, 300) || "",
            articleCount: document.querySelectorAll("article, [class*='card'], li").length,
            bodyClasses: Array.from(document.body.classList).slice(0, 10),
            hasResultsList: !!document.querySelector('[class*="results"]'),
            topClasses: Array.from(document.querySelectorAll("*"))
              .slice(0, 30)
              .map((el) => el.tagName + (el.className ? "." + el.className.slice(0, 30) : ""))
              .filter(Boolean)
              .slice(0, 20),
          };
        })
        .catch(() => ({}));

      log.info(`   DOM preview:`, JSON.stringify(domPreview).slice(0, 1000));

      // Wait for dynamic content
      log.info(`   Waiting 5s more for dynamic content…`);
      await page.waitForTimeout(5000);
      await humanScroll(page);

      // Try card selectors again after waiting
      for (const sel of CARD_SELECTORS) {
        try {
          const count = await page.evaluate((s) => document.querySelectorAll(s).length, sel);
          if (count > 0) {
            cardFound = true;
            usedSelector = `${sel} (${count})`;
            log.info(`Found ${count} cards after delay via "${sel}"`);
            break;
          }
        } catch { /* Selector not found on page, continue */ }
      }
    }

    // Human behaviour + scroll to trigger any lazy-loaded cards.
    if (cardFound) {
      await humanDelay();
      await humanScroll(page);
      await humanDelay();
    }

    // Save raw HTML (used by both extraction paths for provenance).
    const indeedRawPath = await page
      .content()
      .then((content) => saveRawData("indeed", `search_${tag.replace(/[^a-zA-Z0-9]/g, "_")}_page_${pageNum}`, content, "html"))
      .catch(() => null);
    if (indeedRawPath) {
      log.info(`Saved raw HTML: ${indeedRawPath}`);
    }

    // ── Primary path: extract from the rendered DOM ──
    let valid = [];
    if (cardFound) {
      const jobs = await this._extractFromDOM(page);
      valid = jobs.filter((j) => j.title && j.title.length > 1);
      if (jobs.length > 0 && valid.length === 0) {
        log.info(`WARNING: Found ${jobs.length} cards but none had extractable titles`);
      }
      log.info(`Extracted ${valid.length} valid jobs (${jobs.length} total cards)`);
    }

    // ── Fallback path: embedded JSON (SPA state / data-jk / JSON-LD) ──
    // Only used when the DOM path produced nothing usable. Require a title so
    // the empty-title anchors that previously slipped through are dropped here.
    if (valid.length === 0) {
      const embeddedJobs = await this._tryExtractEmbeddedJSON(page);
      const embValid = (embeddedJobs || []).filter((j) => j.title && j.title.trim().length > 1);
      if (embValid.length > 0) {
        log.info(`Extracted ${embValid.length} jobs from embedded page data (fallback)`);
        return this._processJobs(embValid, tag, page, indeedRawPath);
      }

      log.info(`No job cards found after all attempts — returning empty`);
      if (DEBUG) {
        await page.screenshot({ path: `/tmp/indeed_empty_p${pageNum}_${tag}.png`, fullPage: false }).catch(() => {});
        const html = await page.evaluate(() => document.body?.innerHTML?.slice(0, 2000) || "");
        log.info(`   HTML preview: ${html.slice(0, 1000)}`);
      }
      return [];
    }

    // Process and filter jobs
    return this._processJobs(valid, tag, page, indeedRawPath);
  }

  /**
   * Try to extract job data from Indeed's embedded JSON (SPA initial state).
   */
  async _tryExtractEmbeddedJSON(page) {
    try {
      return await page.evaluate(() => {
        const jobs = [];

        // Normalise a salary value (schema.org MonetaryAmount object OR a plain string)
        const salaryToText = (s) => {
          if (!s) return "";
          if (typeof s === "string") return s;
          const v = s.value || s;
          const cur = s.currency || v.currency || "";
          const unit = (v.unitText || "").toString().toLowerCase();
          const per = unit.includes("hour") ? " an hour" : unit.includes("year") ? " a year" : "";
          if (v.minValue != null || v.maxValue != null) {
            return `${v.minValue ?? v.maxValue} - ${v.maxValue ?? v.minValue} ${cur}${per}`.trim();
          }
          if (v.value != null) return `${v.value} ${cur}${per}`.trim();
          return "";
        };

        const extractAssignedObject = (text, marker) => {
          const mi = text.indexOf(marker);
          if (mi === -1) return null;
          const start = text.indexOf("{", mi);
          if (start === -1) return null;
          let depth = 0,
            inStr = false,
            esc = false,
            q = "";
          for (let i = start; i < text.length; i++) {
            const c = text[i];
            if (inStr) {
              if (esc) esc = false;
              else if (c === "\\") esc = true;
              else if (c === q) inStr = false;
            } else if (c === '"' || c === "'") {
              inStr = true;
              q = c;
            } else if (c === "{") depth++;
            else if (c === "}") {
              depth--;
              if (depth === 0) {
                try {
                  return JSON.parse(text.slice(start, i + 1));
                } catch { /* Invalid JSON embedded in script — return null */
                  return null;
                }
              }
            }
          }
          return null;
        };

        // Strategy 1: Look for __INITIAL_STATE__ or __NEXT_DATA__ or similar
        const scripts = document.querySelectorAll("script[type='application/json'], script[type='text/javascript'], script:not([src])");
        for (const script of scripts) {
          const text = script.textContent || "";
          if (!text.includes("job")) continue;
          try {
            const state = extractAssignedObject(text, "window.__INITIAL_STATE__");
            if (state) {
              const jobList = state?.jobSearch?.results || state?.results || state?.jobs;
              if (Array.isArray(jobList)) {
                return jobList.map((j) => ({
                  title: j.title || j.jobTitle || "",
                  company: j.company || j.employer || "",
                  location: j.location || j.jobLocation || "",
                  salary: salaryToText(j.salary || j.estimatedSalary),
                  url: j.url || (j.jobKey ? `https://www.indeed.com/viewjob?jk=${j.jobKey}` : ""),
                  text: (j.snippet || j.description || j.summary || "").slice(0, 1500),
                }));
              }
            }
          } catch { /* Failed to parse __INITIAL_STATE__ — try next strategy */ }
          }

          // Strategy 2: Look for data-jk attributes (Indeed's job key)
        const cards = document.querySelectorAll("[data-jk], [data-jobkey]");
        if (cards.length > 0) {
          return Array.from(cards).map((card) => {
            const jk = card.getAttribute("data-jk") || card.getAttribute("data-jobkey") || "";
            // data-jk usually sits on the jcs-JobTitle anchor itself: its text /
            // aria-label ("full details of <title>") is the reliable title source,
            // since the `[class*='title']` class match is case-sensitive and misses
            // the "jcs-JobTitle" class.
            const titleEl = card.querySelector("h2, h3, span[title]");
            const title =
              (titleEl && (titleEl.getAttribute("title") || titleEl.textContent)?.trim()) ||
              (card.textContent || "").trim().slice(0, 120) ||
              (card.getAttribute("aria-label") || "").replace(/^full details of\s*/i, "").trim() ||
              card.getAttribute("data-title") ||
              "";
            return {
              title,
              company: card.getAttribute("data-company") || card.querySelector("[class*='company']")?.textContent?.trim() || "",
              location: card.getAttribute("data-location") || "",
              salary: card.getAttribute("data-salary") || card.querySelector("[class*='salary']")?.textContent?.trim() || "",
              url: jk ? `https://www.indeed.com/viewjob?jk=${jk}` : "",
              text: card.textContent?.slice(0, 1500) || "",
            };
          });
        }

        // Strategy 3: Look for JSON-LD (schema.org job postings)
        const jsonldScripts = document.querySelectorAll('script[type="application/ld+json"]');
        for (const script of jsonldScripts) {
          try {
            const data = JSON.parse(script.textContent || "{}");
            const items = data?.itemListElement || data?.items || (Array.isArray(data) ? data : [data]);
            for (const item of items) {
              const job = item?.jobPosting || item;
              if (job?.title) {
                jobs.push({
                  title: job.title || "",
                  company: job?.hiringOrganization?.name || "",
                  location: job?.jobLocation?.address?.addressLocality || job?.jobLocation || "",
                  salary: salaryToText(job?.estimatedSalary || job?.baseSalary || job?.salary),
                  url: job?.url || "",
                  text: (job?.description || job?.responsibilities || "").slice(0, 1500),
                });
              }
            }
          } catch { /* Invalid JSON-LD — skip to next script */
            // continue
          }
        }

        return jobs;
      });
    } catch { /* Failed to extract jobs from page — return null */
      log.warn("Failed to extract jobs from page");
      return null;
    }
  }

  /**
   * Extract raw job data from the DOM.
   *
   * Card fields are queried with an ORDERED fallback list (first selector that
   * matches wins). A single comma-joined `querySelector` returns whichever match
   * comes first in document order — not selector order — which caused broad
   * `[class*="company"]` wrappers to shadow the precise `data-testid` fields and
   * return whole-card text blobs. `queryFirst()` restores selector priority.
   */
  async _extractFromDOM(page) {
    return page.evaluate(() => {
      // Pick the narrowest card selector that actually matches, instead of
      // unioning them all (which pulled in generic `.card`/`li` wrappers and
      // produced dozens of empty phantom cards).
      const CARD_SELECTORS = [
        '[data-testid="slider_item"]',
        '[class*="job_seen_beacon"]',
        '[data-testid="search-result"]',
        '[data-testid*="job-card"]',
        '[class*="JobCard"]',
        '[class*="job-card"]',
        '[class*="job-result"]',
        "li[class*='job']",
      ];
      let cards = [];
      for (const sel of CARD_SELECTORS) {
        const found = document.querySelectorAll(sel);
        if (found.length) {
          cards = Array.from(found);
          break;
        }
      }
      if (cards.length === 0) return [];

      // First matching element across an ORDERED selector list.
      const queryFirst = (root, selectors) => {
        for (const sel of selectors) {
          const el = root.querySelector(sel);
          if (el) return el;
        }
        return null;
      };
      const cleanText = (el) => (el?.textContent || "").replace(/\s+/g, " ").trim();

      const seen = new Set();

      return cards
        .filter((card) => {
          const key = card.textContent?.slice(0, 100) || "";
          if (seen.has(key)) return false;
          seen.add(key);
          return true;
        })
        .map((card) => {
          // ── Title ── The old `data-testid="jobTitle"` is gone; the title now
          // lives in the `jcs-JobTitle` anchor (aria-label "full details of …")
          // wrapped in an <h2>, with the visible label in a nested <span title>.
          const titleAnchor = queryFirst(card, [
            'a.jcs-JobTitle',
            'a[class*="jcs-JobTitle"]',
            'a[data-jk]',
            'h2 a',
          ]);
          const titleSpan = queryFirst(card, ['h2 span[title]', 'a.jcs-JobTitle span', 'h2 span']);
          let title = "";
          if (titleSpan) title = (titleSpan.getAttribute("title") || cleanText(titleSpan)).trim();
          if (!title && titleAnchor) {
            title = cleanText(titleAnchor) ||
              (titleAnchor.getAttribute("aria-label") || "").replace(/^full details of\s*/i, "").trim();
          }
          if (!title) title = cleanText(queryFirst(card, ['[data-testid="jobTitle"]', 'h2', 'h3']));

          // ── Company ── precise testid first, then legacy classes.
          const company = cleanText(
            queryFirst(card, [
              '[data-testid="company-name"]',
              '[data-testid="companyName"]',
              '.companyName',
              'span[data-testid="company-name"]',
            ])
          );

          // ── Location ── precise testid only (broad [class*=location] over-matches).
          const location = cleanText(
            queryFirst(card, [
              '[data-testid="text-location"]',
              '[data-testid="job-location"]',
              '.companyLocation',
            ])
          );

          // ── Salary ── snippet attributes, then a metadata scan.
          let salary = cleanText(
            queryFirst(card, [
              '[data-testid="attribute_snippet_testid"]',
              '[data-testid="estimated-salary"]',
              '[class*="salary-snippet"]',
              '[class*="salaryOnly"]',
            ])
          );
          if (!salary || !/\d/.test(salary)) {
            const metaEls = card.querySelectorAll('[class*="metadata"], [data-testid="attribute_snippet_testid"], li');
            for (const el of metaEls) {
              const t = (el.textContent || "").replace(/\s+/g, " ").trim();
              if (/[$€£zł]/.test(t) || /\byear\b|\bhour\b|\ba year\b|\ban hour\b|salary/i.test(t)) {
                salary = t;
                break;
              }
            }
          }

          // ── URL ── from the title anchor (data-jk is Indeed's canonical key).
          let url = "";
          const jk = titleAnchor?.getAttribute("data-jk") || card.getAttribute("data-jk") || "";
          const href = titleAnchor?.getAttribute("href") ||
            queryFirst(card, ['a[href*="/rc/clk"]', 'a[href*="/viewjob"]', 'a[href*="/job/"]'])?.getAttribute("href") || "";
          if (jk) {
            url = `https://www.indeed.com/viewjob?jk=${jk}`;
          } else if (href) {
            url = href.startsWith("http") ? href : `https://www.indeed.com${href.startsWith("/") ? "" : "/"}${href}`;
          }

          // ── Snippet ── description text drives tag matching + skill extraction.
          const snippet = cleanText(
            queryFirst(card, ['[data-testid="belowJobSnippet"]', '[class*="job-snippet"]', '.underShelfFooter'])
          );

          return {
            title,
            company,
            location,
            salary,
            url,
            text: `${title} ${snippet} ${cleanText(card)}`.slice(0, 1500),
            dateText: cleanText(
              queryFirst(card, ['span[data-testid="myJobsStateDate"]', '[class*="date"]'])
            ),
          };
        });
    });
  }

  /**
   * Process raw job objects: parse salary, extract skills, filter by tag, build output.
   */
  _processJobs(rawJobs, tag, page, rawPath) {
    const results = [];
    const domain = this._domain;

    for (const job of rawJobs) {
      const rawText = job.title + " " + job.text;
      const text = rawText.toLowerCase();
      const tagMatch = matchesAnyTag(TAG_SET, text);
      if (!tagMatch) continue;

      const sal = this._parseSalary(job.salary);
      const techStack = extractSkills(rawText);
      const isRemote = /remote/i.test(job.location || job.text);

      // Parse Indeed date text
      let publishedAt = null;
      if (job.dateText) {
        const dt = job.dateText.toLowerCase();
        if (
          dt.includes("przed chwil") ||
          dt.includes("dzisiaj") ||
          dt.includes("today") ||
          dt.includes("moments") ||
          dt.includes("just now")
        ) {
          // Fresh — use current date
        } else if (dt.includes("dni temu") || dt.includes("days ago")) {
          const dayMatch = dt.match(/\d+/);
          if (dayMatch) {
            const daysAgo = parseInt(dayMatch[0], 10);
            if (daysAgo <= 30) {
              const d = new Date();
              d.setDate(d.getDate() - daysAgo);
              publishedAt = d.toISOString();
            }
          }
        } else if (dt.includes("godzin") || dt.includes("hour") || dt.includes("minut")) {
          // Hours/minutes ago — use current date
        }
      }

      const output = {
        external_id: `indeed_${stableId(job.url || job.title + job.company)}`,
        platform: "indeed.com",
        title: job.title,
        company: job.company || "Unknown",
        url: job.url || `https://${domain}/jobs?q=${encodeURIComponent(tag)}`,
        salary_min: sal.salary_min,
        salary_max: sal.salary_max,
        currency: sal.currency || "USD",
        contract_type: "B2B",
        location: job.location || (isRemote ? "Remote" : ""),
        remote: isRemote,
        skills: [...new Set(techStack)],
        category: "",
        experience_level: "",
        requirements: job.text.slice(0, 2000),
        discovered_at: new Date().toISOString(),
        nice_to_have_skills: "[]",
        languages: "[]",
        published_at: publishedAt,
        expired_at: null,
        last_published_at: null,
        working_time: "full_time",
        latitude: null,
        longitude: null,
        street: "",
        _raw: rawPath ? [rawPath] : [],
      };

      results.push(output);
    }

    return results;
  }

  /**
   * Parse salary text using shared salary utilities with Indeed-specific fallbacks.
   * @param {string} text
   * @returns {{ salary_min: number|null, salary_max: number|null, currency: string }}
   */
  _parseSalary(text) {
    if (typeof text !== "string") text = text ? String(text) : "";
    if (!text) return { salary_min: null, salary_max: null, currency: "USD" };

    const currency = detectCurrency(text) || "USD";

    // Try shared hourly rate → yearly conversion first
    const hourly = parseHourlyRateToYearly(text);
    if (hourly.salary_min !== null || hourly.salary_max !== null) {
      return { salary_min: hourly.salary_min, salary_max: hourly.salary_max, currency };
    }

    // Try shared range parser (handles "100k - 200k", "$100k", etc.)
    const range = parseSalaryRange(text);
    if (range.salary_min !== null || range.salary_max !== null) {
      return { salary_min: range.salary_min, salary_max: range.salary_max, currency: range.currency || currency };
    }

    // Indeed-specific patterns not covered by shared functions

    // "From $X an hour" or "$X - $Y an hour" → convert to yearly (× 2080)
    const clean = text.replace(/,/g, "").replace(/\s+/g, " ");
    const hourlyMatch = clean.match(/\$?(\d+[\.,\d]*)\s*[--—to]*\s*\$?(\d+[\.,\d]*)\s*\/{0,1}\s*(hr|hour)/i);
    if (hourlyMatch) {
      const a = parseFloat(hourlyMatch[1].replace(/,/g, "")) * 2080;
      const b = parseFloat(hourlyMatch[2].replace(/,/g, "")) * 2080;
      return { salary_min: Math.round(Math.min(a, b)), salary_max: Math.round(Math.max(a, b)), currency };
    }

    // "From $X/hr" or "$X+/hr"
    const minHourly = clean.match(/\$?(\d+[\.,\d]*)\+?\s*\/{0,1}\s*(hr|hour)/i);
    if (minHourly) {
      const val = parseFloat(minHourly[1].replace(/,/g, ""));
      return { salary_min: Math.round(val * 2080), salary_max: null, currency };
    }

    // "$X - $Y a year" or "From $X a year"
    const yearlyMatch = clean.match(/\$?(\d+[\.,\d]*)\s*[--—to]*\s*\$?(\d+[\.,\d]*)\s*\/{0,1}\s*(year|yr|annum)/i);
    if (yearlyMatch) {
      const a = parseFloat(yearlyMatch[1].replace(/,/g, ""));
      const b = parseFloat(yearlyMatch[2].replace(/,/g, ""));
      return { salary_min: Math.round(Math.min(a, b)), salary_max: Math.round(Math.max(a, b)), currency };
    }

    const singleYearly = clean.match(/\$?(\d+[\.,\d]*)\s*\/{0,1}\s*(year|yr|annum)/i);
    if (singleYearly) {
      const val = parseFloat(singleYearly[1].replace(/,/g, ""));
      return { salary_min: Math.round(val), salary_max: null, currency };
    }

    // "$X - $Y" bare (assume yearly, but if both < 200, assume hourly × 2080)
    const bareMatch = clean.match(/\$?(\d+[\.,\d]*)\s*[--—to]*\s*\$?(\d+[\.,\d]*)/);
    if (bareMatch) {
      const a = parseFloat(bareMatch[1].replace(/,/g, ""));
      const b = parseFloat(bareMatch[2].replace(/,/g, ""));
      if (a > 0 && b > 0) {
        if (a < 200 && b < 200) {
          return { salary_min: Math.round(a * 2080), salary_max: Math.round(b * 2080), currency };
        }
        return { salary_min: Math.round(Math.min(a, b)), salary_max: Math.round(Math.max(a, b)), currency };
      }
    }

    // "From $X" single value (assume yearly if > 200, else hourly)
    const singleVal = clean.match(/\$?(\d{3,})/);
    if (singleVal) {
      const val = parseFloat(singleVal[1].replace(/,/g, ""));
      if (val > 200) {
        return { salary_min: Math.round(val), salary_max: null, currency };
      }
    }

    return { salary_min: null, salary_max: null, currency };
  }
}

// ─── Main ───────────────────────────────────────────────────────────────
async function main() {
  const scraper = new IndeedScraper({
    maxPages: MAX_PAGES,
    headless: true,
    blockResources: true,
    proxyEnabled: true,
    country: SCRAPER_CFG ? SCRAPER_CFG.country : undefined,
  });
  const result = await scraper.scrape();
  writeOutput("indeed", result.jobs);
  log.info(`${result.jobs.length} matching offers`);
  printTopJobs("[indeed]", result.jobs);
  return result;
}

if (require.main === module) {
  main().catch((err) => {
    console.error("[indeed] Fatal:", err);
    process.exit(1);
  });
}

module.exports = {
  metadata: {
    id: "indeed",
    name: "Indeed",
    capabilities: ["browser"],
    needsBrowser: true,
    platform: "indeed.com",
    configFields: {
      max_pages: {
        type: "number",
        label: "Max Pages",
        description: "Maximum number of pagination pages to scrape",
        default: 3,
        min: 1,
        max: 100,
        unit: "pages",
      },
      country: {
        type: "string",
        label: "Country",
        description: "Two-letter country code for Indeed subdomain (e.g. pl, de, uk, us). Default: us",
        default: "us",
        enum: ["us", "pl", "de", "uk", "fr", "es", "nl", "it", "jp", "au", "ca", "in"],
      },
    },
  },
  main,
  register(registry) {
    registry.register(this);
  },
};
