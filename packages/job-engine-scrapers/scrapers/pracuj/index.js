#!/usr/bin/env node
/**
 * Pracuj.pl Scraper — extends BrowserScraper.
 *
 * Two-phase approach:
 * 1. **Listing phase** — navigate to search result pages via Playwright
 *    and extract title, company, salary, location, contract type, and remote/hybrid
 *    flags from the rendered DOM. Pagination via ?pn=N.
 *    Supports ALL contract types (UoP, B2B, UZ, UD, etc.).
 * 2. **Detail phase** — navigate to each unique job detail page in the same browser
 *    to extract skills, full description, and JSON-LD structured data.
 *    Uses concurrent worker pool with a single shared page.
 *
 * Why Playwright (not HTTP fetch):
 *   pracuj.pl is behind Cloudflare protection that returns HTTP 403 to plain HTTP
 *   requests. A real browser executes the Cloudflare challenge JS and receives the
 *   actual content. Both listing and detail pages are server-rendered HTML that is
 *   fully available once the browser loads the page.
 *
 * No unnecessary delays:
 *   - No waitForTimeout / humanDelay calls — server-rendered pages are ready at
 *     domcontentloaded. Cloudflare challenges resolve within the waitForSelector
 *     timeout.
 *   - A single shared page is used for all navigation (no newPage() overhead).
 *   - Fast navigation timeouts (15s) prevent hanging.
 */

const log = require("@job-engine-scrapers/core").logger("pracuj");
const { extractSkills } = require("@job-engine-scrapers/core").skills;
const { writeOutput, printTopJobs, saveRawData } = require("@job-engine-scrapers/core").output;
const { stableId, SeenJobsDB } = require("@job-engine-scrapers/core").dedup;
const BrowserScraper = require("@job-engine-scrapers/core").browserScraper;
const config = require("@job-engine-scrapers/core").config;
const { parseSalaryRange, detectPeriod } = require("@job-engine-scrapers/core").salary;

const SCRAPER_CFG = config.getScraper("pracuj");
const MAX_PAGES = SCRAPER_CFG ? SCRAPER_CFG.max_pages ?? 1 : 1;
const DETAIL_CONCURRENCY = parseInt(SCRAPER_CFG?.detail_concurrency || 5, 10);
const REQUEST_DELAY_MS = parseInt(SCRAPER_CFG?.request_delay_ms || 500, 10);
const MAX_ENRICH_JOBS_PER_RUN = parseInt(SCRAPER_CFG?.max_enrich_jobs || 200, 10);
const NAV_TIMEOUT = 15000;

// Incremental enrichment DB — persists which job URLs have been detail-enriched
// so each run only fetches new/expired entries.
const enrichDb = new SeenJobsDB({
  filePath: process.env.PRACUJ_ENRICH_DB
    || require("path").join(__dirname, "..", "..", "..", "data", "scraper-output", "pracuj_enrich_db.json"),
  ttlDays: 14,
});

// Use search terms (boosted keywords) instead of all 78 tags
const SEARCH_TERMS = config.getSearchTerms();

// Every offer link on pracuj.pl follows this pattern regardless of page markup.
const OFFER_LINK_RE = /\/praca\/[^"' ]+,oferta,\d+/;

// ——————————————————————————————————————————————————————————————————————————
//  PracujScraper class — extends BrowserScraper
// ——————————————————————————————————————————————————————————————————————————

class PracujScraper extends BrowserScraper {
  get id() { return "pracuj"; }
  get platform() { return "pracuj.pl"; }

  buildUrl(tag, pageNum) {
    return `https://www.pracuj.pl/praca/${encodeURIComponent(tag)};kw?pn=${pageNum}`;
  }

  /** Override navigateToPage with a shorter 15s timeout for pracuj.pl */
  async navigateToPage(page, url) {
    try {
      await page.goto(url, { waitUntil: "domcontentloaded", timeout: NAV_TIMEOUT });
    } catch (err) {
      log.info(`[${this.id}] Navigation failed for ${url} (${err.message})`);
      return false;
    }
    const blocked = await this.detectWaf(page);
    if (blocked) {
      log.info(`[${this.id}] WAF/blocking detected at ${url}`);
      if (this.debug) {
        await page.screenshot({ path: `/tmp/${this.id}_blocked.png`, fullPage: false }).catch(() => {});
      }
      return false;
    }
    return true;
  }

  /** Extract jobs from a listing page — called after navigation + WAF check */
  async extractJobs(page, tag, pageNum) {
    log.info(`[${this.id}] Fetching page ${pageNum} for "${tag}"`);

    // Wait for tiles to appear (gives Cloudflare time to resolve)
    await page.waitForSelector(
      '[data-test="default-offer"], [data-test="positioned-offer"]',
      { timeout: 10000 }
    ).catch(() => {
      // No tiles — try fallback
    });

    // Extract tiles from rendered DOM
    const tiles = await page.evaluate((offerLinkRe) => {
      const results = [];

      // Primary: data-test attributes
      const offers = document.querySelectorAll(
        '[data-test="default-offer"], [data-test="positioned-offer"]'
      );
      offers.forEach((el) => {
        const infos = [0, 1, 2, 3, 4, 5, 6]
          .map((i) => {
            const infoEl = el.querySelector(`[data-test="offer-additional-info-${i}"]`);
            return infoEl?.textContent?.trim() || "";
          })
          .filter(Boolean);

        const linkEl = el.querySelector(
          'a[data-test="link-offer-title"], a[data-test="link-offer"]'
        );

        results.push({
          offerId: el.getAttribute("data-test-offerid") || "",
          title: el.querySelector('[data-test="offer-title"]')?.textContent?.trim() || "",
          company: el.querySelector('[data-test="text-company-name"]')?.textContent?.trim() || "Unknown",
          salary: el.querySelector('[data-test="offer-salary"]')?.textContent?.trim() || "",
          region: el.querySelector('[data-test="text-region"]')?.textContent?.trim() || "",
          href: linkEl?.getAttribute("href") || "",
          infos,
        });
      });

      // Fallback: offer URL pattern
      if (results.length === 0) {
        const seen = new Set();
        const allLinks = document.querySelectorAll("a");
        const pattern = new RegExp(offerLinkRe);

        allLinks.forEach((el) => {
          const href = el.getAttribute("href") || "";
          const match = href.match(pattern);
          if (!match || seen.has(href)) return;
          seen.add(href);

          const container = el.closest("li, div, article") || el;
          const text = container.textContent || "";
          const lines = text.split("\n").map((l) => l.trim()).filter(Boolean);

          const title = el.textContent?.trim() || "";
          const company = lines.find((l) => l !== title && l.length > 0 && l.length < 100) || null;
          const idMatch = href.match(/,oferta,(\d+)/);

          results.push({
            offerId: idMatch?.[1] || href,
            title: title || "Unknown",
            company,
            salary: "",
            region: "",
            href: href.startsWith("http") ? href : `https://www.pracuj.pl${href}`,
            infos: [],
          });
        });
      }

      return results;
    }, OFFER_LINK_RE.source);

    log.info(`[${this.id}] Found ${tiles.length} tiles on page ${pageNum}`);

    // ── Extract __NEXT_DATA__ from the listing page (contains rich per-offer data) ──
    // The listing page's Next.js __NEXT_DATA__ script includes aiSummary (HTML with
    // skill tags), jobDescription, positionLevels, workModes, salaryDisplayText, and
    // clean offer URLs for every job on the page.  The detail enrichment phase
    // (Cloudflare-blocked) often fails to extract these, so we backfill from the
    // listing page's structured data here.
    const nextDataStr = await page.evaluate(() => {
      const script = document.getElementById("__NEXT_DATA__");
      return script?.textContent || "{}";
    });
    let nextDataMap = {};
    try {
      const nextData = JSON.parse(nextDataStr);
      const queries =
        nextData?.props?.pageProps?.dehydratedState?.queries || [];
      for (const q of queries) {
        const qdata = q?.state?.data;
        if (!qdata || typeof qdata !== "object") continue;
        const grouped = qdata.groupedOffers;
        if (!Array.isArray(grouped)) continue;
        for (const group of grouped) {
          if (!group || typeof group !== "object") continue;
          const shared = {
            jobTitle: group.jobTitle || "",
            companyName: group.companyName || "",
            aiSummary: group.aiSummary || "",
            jobDescription: group.jobDescription || "",
            positionLevels: group.positionLevels || [],
            typesOfContract: group.typesOfContract || [],
            workModes: group.workModes || [],
            workSchedules: group.workSchedules || [],
            salaryDisplayText: group.salaryDisplayText || "",
            isRemoteWorkAllowed: group.isRemoteWorkAllowed === true,
            lastPublicated: group.lastPublicated || "",
            companyLogoUri: group.companyLogoUri || "",
          };
          for (const offer of group.offers || []) {
            if (!offer || typeof offer !== "object") continue;
            const uri = offer.offerAbsoluteUri || "";
            const idMatch = uri.match(/,oferta,(\d+)/);
            if (idMatch) {
              nextDataMap[idMatch[1]] = {
                ...shared,
                displayWorkplace: offer.displayWorkplace || "",
                cleanUrl: uri,
                isRemote: offer.isRemote,
                isHybrid: offer.isHybrid,
              };
            }
          }
        }
      }
    } catch (err) {
      log.warn(`[${this.id}] Failed to parse __NEXT_DATA__: ${err.message}`);
    }
    if (Object.keys(nextDataMap).length > 0) {
      log.info(`[${this.id}] Extracted __NEXT_DATA__ for ${Object.keys(nextDataMap).length} offers`);
    }

    // Save raw listing HTML
    await pracujSaveListingRaw(page, tag, pageNum);

    // Normalize tiles into job objects, merging __NEXT_DATA__ where available
    const jobs = [];
    for (const raw of tiles) {
      const job = normalize(raw, nextDataMap);
      if (job) jobs.push(job);
    }

    return jobs;
  }

  /** Override scrape() to add detail enrichment phase after listing */
  async scrape() {
    const allJobs = new Map();
    const tags = this.getSearchTags();
    const cfg = this.getScraperConfig();
    const maxPages = cfg.max_pages || this.maxPages;
    this.debug = cfg.debug || process.env[`${this.id.toUpperCase()}_DEBUG`] === "1";

    log.info(`[${this.id}] Starting (${tags.length} search terms, max ${maxPages} pages/term)`);

    // Prune stale enrichment state before we start
    const pruned = enrichDb.cleanup();
    if (pruned > 0) log.info(`[${this.id}] Cleaned ${pruned} stale entries from enrichment DB`);
    const alreadyEnriched = enrichDb.count("evaluated");
    log.info(`[${this.id}] Enrichment DB: ${alreadyEnriched} already enriched, ${enrichDb.count()} total`);

    try {
      await this.launch();
      if (!this.page) {
        log.error(`[${this.id}] Failed to launch browser`);
        return { platform: this.platform, count: 0, jobs: [] };
      }

      // Phase 1: Listing pages
      for (const tag of tags) {
        for (let p = 1; p <= maxPages; p++) {
          if (p > 1) {
            await this.rotateFingerprint();
          }
          await this.randomMouseMoves(this.page);

          const url = this.buildUrl(tag, p);
          log.info(`[${this.id}] Searching "${tag}" page ${p}/${maxPages}`);

          const ok = await this.navigateToPage(this.page, url);
          if (!ok) {
            log.info(`[${this.id}] Navigation failed/blocked on page ${p} — stopping`);
            break;
          }

          await this.applyHumanBehavior();

          let rawJobs = [];
          try {
            rawJobs = await this.extractJobs(this.page, tag, p);
          } catch (err) {
            log.warn(`[${this.id}] Extract error on page ${p}: ${err.message}`);
            if (this.debug) {
              await this.page.screenshot({ path: `/tmp/${this.id}_error_p${p}.png`, fullPage: false }).catch(() => {});
            }
            break;
          }

          if (rawJobs.length === 0) {
            log.info(`[${this.id}] No jobs on page ${p} — stopping`);
            break;
          }

          for (const job of rawJobs) {
            if (job.external_id && !allJobs.has(job.external_id)) {
              allJobs.set(job.external_id, job);
            }
          }
        }
      }

      let jobs = [...allJobs.values()];
      log.info(`[${this.id}] Listing phase done — ${jobs.length} offers collected`);

      // Phase 2: Detail enrichment (incremental)
      if (jobs.length > 0) {
        const needEnrich = jobs.filter((j) => enrichDb.isNew(j.url));
        const skipEnrich = jobs.length - needEnrich.length;
        log.info(`[${this.id}] ${skipEnrich}/${jobs.length} already enriched, ${needEnrich.length} need detail fetch`);

        if (needEnrich.length > 0) {
          const batch = needEnrich.length > MAX_ENRICH_JOBS_PER_RUN
            ? needEnrich.slice(0, MAX_ENRICH_JOBS_PER_RUN)
            : needEnrich;
          log.info(`[${this.id}] Enriching ${batch.length}/${needEnrich.length} this run (cap: ${MAX_ENRICH_JOBS_PER_RUN})`);

          await enrichJobs(batch, this.page, DETAIL_CONCURRENCY);

          // Persist enrichment state so next run skips these
          for (const job of batch) {
            enrichDb.mark(job.url, "evaluated");
          }
          enrichDb.save();
          const newEval = enrichDb.count("evaluated");
          log.info(`[${this.id}] Enrichment DB now has ${newEval} evaluated jobs`);
        }
      }

    } catch (err) {
      log.error(`[${this.id}] Fatal scrape error: ${err.message}`);
    } finally {
      await this.close();
    }

    const jobs = [...allJobs.values()];
    log.info(`[${this.id}] ${jobs.length} matching offers`);
    return { platform: this.platform, count: jobs.length, jobs };
  }
}

/**
 * Save listing page content as raw HTML.
 */
async function pracujSaveListingRaw(page, tag, pageNum) {
  try {
    const rawPath = saveRawData("pracuj", `listing_${tag.replace(/[^a-zA-Z0-9]/g, "_")}_page_${pageNum}`, await page.content(), "html");
    if (rawPath) log.info(`Saved raw listing HTML: ${rawPath}`);
    return rawPath;
  } catch { return null; /* Save failure is non-critical */ }
}

// ——————————————————————————————————————————————————————————————————————————
//  Phase 2: Detail page enrichment (browser-based, single shared page)
// ——————————————————————————————————————————————————————————————————————————

/**
 * Extract skills, requirements, and metadata from a job detail page.
 * No waitForTimeout — server-rendered pages are ready at domcontentloaded.
 */
async function scrapeDetailPage(page, job) {
  if (!job.url) return;

  try {
    await page.goto(job.url, { waitUntil: "domcontentloaded", timeout: NAV_TIMEOUT });
  } catch (err) {
    log.info(`Detail navigation failed: ${err.message}`);
    return;
  }

  // Save detail page raw HTML
  try {
    const detailRawPath = saveRawData("pracuj", `detail_${stableId(job.external_id || job.url)}`, await page.content(), "html");
    if (detailRawPath) {
      if (!job._raw) job._raw = [];
      job._raw.push(detailRawPath);
    }
  } catch { /* Non-critical — skip if raw data save fails */ }

  // Extract data from rendered page
  const detailData = await page.evaluate(() => {
    const result = {
      jsonld: null,
      pageSkills: "",
      pageText: "",
      h1: "",
      h2: "",
      salaryText: "",
      descHtml: "",
    };

    // ── Strategy 1: Extract JSON-LD structured data ──
    const scripts = document.querySelectorAll('script[type="application/ld+json"]');
    for (const script of scripts) {
      try {
        const data = JSON.parse(script.textContent || "{}");
        const posting = data["@graph"]
          ? data["@graph"].find((g) => g["@type"] === "JobPosting")
          : data["@type"] === "JobPosting"
            ? data
            : null;
        if (posting) {
          result.jsonld = posting;
          break;
        }
      } catch { /* Skip invalid JSON */ }
    }

    // ── Strategy 2: Extract skills from technology tags ──
    const techElements = document.querySelectorAll(
      '[data-test*="tech"], [data-test*="skill"], [data-test*="technology"], ' +
      '[class*="skill"], [class*="tech"], [class*="technology"], ' +
      '[class*="tags"]'
    );
    result.pageSkills = Array.from(techElements)
      .map((el) => el.textContent?.trim() || "")
      .filter(Boolean)
      .join(" ");

    // ── Strategy 3: Full page text ──
    result.pageText = document.body?.textContent?.trim() || "";

    // Headings for gap-filling
    result.h1 = document.querySelector("h1")?.textContent?.trim() || "";
    result.h2 = document.querySelector("h2")?.textContent?.trim() || "";

    // Salary from detail page
    result.salaryText = document.querySelector('[data-test="offer-salary"]')?.textContent?.trim() || "";

    // Description fallback
    const detailsEl = document.getElementById("offer-details");
    if (detailsEl) {
      result.descHtml = detailsEl.textContent?.trim() || "";
    } else {
      const mainEl = document.querySelector("main, article");
      result.descHtml = mainEl?.textContent?.trim() || "";
    }

    return result;
  }).catch(() => ({
    jsonld: null, pageSkills: "", pageText: "", h1: "", h2: "",
    salaryText: "", descHtml: "",
  }));

  // ── Merge all sources ──

  // Skills: from JSON-LD + regex extraction
  const jsonLdSkills = detailData.jsonld
    ? [detailData.jsonld.skills, detailData.jsonld.occupationalCategory,
       detailData.jsonld.qualifications, detailData.jsonld.educationRequirements]
        .filter(Boolean)
        .flatMap((s) => (typeof s === "string" ? [s] : s))
        .join(" ")
    : "";

  const extracted = extractSkills(detailData.pageSkills || detailData.pageText);
  const allSkills = [...extracted, ...extractSkills(jsonLdSkills)];
  const uniqueSkills = [...new Set(allSkills)];

  if (uniqueSkills.length > 0) {
    job.skills = uniqueSkills;
  }

  // Requirements/description
  if (detailData.jsonld?.description) {
    job.requirements = detailData.jsonld.description;
  } else if (detailData.descHtml && detailData.descHtml.length > 200) {
    job.requirements = detailData.descHtml.slice(0, 5000);
  }

  // Experience level from JSON-LD
  if (detailData.jsonld?.experienceRequirements?.minimumExperienceMonths) {
    const months = detailData.jsonld.experienceRequirements.minimumExperienceMonths;
    if (months >= 48) job.experience_level = "Senior";
    else if (months >= 24) job.experience_level = "Mid";
    else if (months >= 0) job.experience_level = "Junior";
  }

  // Fill gaps from detail page headings
  if (!job.title || job.title === "Unknown") {
    job.title = detailData.h1 || job.title;
  }
  if (!job.company || job.company === "Unknown") {
    job.company = detailData.h2 || job.company;
  }
  if (!job.salary_min && !job.salary_max && detailData.salaryText) {
    const parsed = parseSalary(detailData.salaryText);
    if (parsed.min || parsed.max) {
      job.salary_min = parsed.min;
      job.salary_max = parsed.max;
      job.salary_period = parsed.period;
    }
  }
}

/**
 * Enrich all jobs with detail-page data using a shared browser page.
 * Each worker navigates the shared page sequentially (no concurrent page usage)
 * to avoid Playwright navigation race conditions.
 */
async function enrichJobs(jobs, page, concurrency) {
  if (jobs.length === 0) return;
  log.info(`Enriching ${jobs.length} jobs from detail pages (concurrency: ${concurrency})…`);

  let cursor = 0;

  async function worker() {
    while (cursor < jobs.length) {
      const job = jobs[cursor++];
      try {
        await scrapeDetailPage(page, job);
        // Polite delay between requests to avoid rate-limiting
        await new Promise((r) => setTimeout(r, REQUEST_DELAY_MS));
      } catch { /* Individual detail failure doesn't crash the batch */
        // Individual detail failure doesn't crash the batch
      }
    }
  }

  const workers = Array.from({ length: Math.max(1, concurrency) }, () => worker());
  await Promise.all(workers);

  const withSkills = jobs.filter(j => j.skills && j.skills.length > 0);
  log.info(`Detail enrichment done — ${withSkills.length}/${jobs.length} jobs have skills extracted`);
}

// ——————————————————————————————————————————————————————————————————————————
//  Normalization
// ——————————————————————————————————————————————————————————————————————————

/** Strip ?searchId=... query param from URLs */
function removeSearchId(url) {
  if (!url) return url;
  const idx = url.indexOf("?searchId=");
  return idx !== -1 ? url.slice(0, idx) : url;
}

/**
 * Detect contract type from listing infos.
 * Maps Polish contract type names to standardised values.
 */
function detectContractType(infos) {
  const joined = infos.join(" ").toLowerCase();
  if (joined.includes("b2b")) return "B2B";
  if (joined.includes("umowa o prac") || joined.includes("uop") || joined.includes("permanent")) return "PERMANENT";
  if (joined.includes("umowa zlecenie") || joined.includes("uz") || joined.includes("mandate")) return "UZ";
  if (joined.includes("umowa o dzie") || joined.includes("ud") || joined.includes("specific-work")) return "UD";
  if (joined.includes("contract")) return "contract";
  if (joined.includes("freelance")) return "freelance";
  if (joined.includes("part time") || joined.includes("part_time")) return "part_time";
  if (joined.includes("full time") || joined.includes("full_time")) return "full_time";
  if (joined.includes("intern") || joined.includes("staż") || joined.includes("praktyk")) return "internship";
  // Default: detect from B2B/UoP patterns in the full listing text
  if (joined.includes("umowa")) return "contract";
  return "other";
}

function parseSalary(str) {
  if (!str) return { min: null, max: null, period: null, currency: "PLN" };
  const period = detectPeriod(str) || null;
  // Polish salary format uses spaces as thousand separators: "5 000 – 10 000 zł / mies."
  // Pre-process: remove spaces from digit sequences before passing to parseSalaryRange
  const normalized = str.replace(/(\d)\s+(?=\d)/g, '$1$2');
  const result = parseSalaryRange(normalized);
  return {
    min: result.salary_min,
    max: result.salary_max,
    period: period,
    currency: result.currency || "PLN",
  };
}

function parseRegion(region) {
  if (!region) return "Poland";
  const m = region.match(/Miejsce pracy:(.+?)(?:Siedziba firmy:|$)/);
  return (m ? m[1] : region).trim() || "Poland";
}

function normalize(raw, nextDataMap = {}) {
  // Defensive: skip entries with missing required fields early
  if (!raw.offerId) return null;
  const href = removeSearchId(raw.href);
  if (!href) return null;

  const sal = parseSalary(raw.salary);
  const isRemote = raw.infos.some((i) => i === "Praca zdalna" || i.includes("zdalna"));
  const isHybrid = raw.infos.some((i) => i === "Praca hybrydowa" || i.includes("hybrydowa"));
  const experience = raw.infos.find((i) => /specjalist|ekspert|junior|stażyst|praktykant|kierownik|dyrektor|młodszy|mid|senior/i.test(i)) ?? "";

  // Map Polish experience levels to English
  const expMap = {
    "młodszy": "junior",
    "stażyst": "intern",
    "praktykant": "intern",
    "junior": "junior",
    "mid": "mid",
    "specjalist": "mid",
    "ekspert": "senior",
    "senior": "senior",
    "kierownik": "manager",
    "dyrektor": "director",
  };
  const expLevel = experience
    ? Object.entries(expMap).find(([pl]) => experience.toLowerCase().includes(pl))?.[1] ?? experience
    : "";

  const contractType = detectContractType(raw.infos);

  // ── Merge __NEXT_DATA__ (rich structured data from listing page) ─────────
  const nd = nextDataMap[raw.offerId] || {};

  // Extract skills from aiSummary (HTML with <b> tags around skill names)
  let skillsFromAi = [];
  if (nd.aiSummary) {
    // Strip HTML tags to get plain text, then extract skill keywords
    const plainText = nd.aiSummary.replace(/<[^>]+>/g, " ");
    skillsFromAi = extractSkills(plainText);
  }

  // Use clean URL from __NEXT_DATA__ if available (strips ?searchId= garbage)
  const cleanUrl = nd.cleanUrl || href;

  // Build description from jobDescription (fall back to empty string if not available)
  const description = nd.jobDescription || "";

  // Override contract type from __NEXT_DATA__ if DOM infos didn't detect it
  let enrichedContractType = contractType;
  if (contractType === "other" && nd.typesOfContract?.length > 0) {
    const joined = nd.typesOfContract.join(" ").toLowerCase();
    if (joined.includes("b2b")) enrichedContractType = "B2B";
    else if (joined.includes("umowa o prac") || joined.includes("uop")) enrichedContractType = "PERMANENT";
    else if (joined.includes("umowa zlecenie") || joined.includes("uz")) enrichedContractType = "UZ";
    else if (joined.includes("umowa o dzie") || joined.includes("ud")) enrichedContractType = "UD";
  }

  // Override remote/hybrid from __NEXT_DATA__ if DOM didn't detect it
  let enrichedRemote = isRemote;
  let enrichedHybrid = isHybrid;
  if (!isRemote && !isHybrid && nd.workModes?.length > 0) {
    const modes = nd.workModes.join(" ").toLowerCase();
    enrichedRemote = modes.includes("zdalna");
    enrichedHybrid = modes.includes("hybrydowa");
  }
  if (nd.isRemoteWorkAllowed && !enrichedRemote && !enrichedHybrid) {
    enrichedRemote = true;
  }

  // Override experience level from __NEXT_DATA__ positionLevels
  let enrichedExp = expLevel;
  if (!expLevel && nd.positionLevels?.length > 0) {
    const joined = nd.positionLevels.join(" ").toLowerCase();
    if (joined.includes("senior") || joined.includes("ekspert") || joined.includes("starszy")) enrichedExp = "senior";
    else if (joined.includes("mid") || joined.includes("specjalist")) enrichedExp = "mid";
    else if (joined.includes("junior") || joined.includes("młodszy")) enrichedExp = "junior";
    else if (joined.includes("stażyst") || joined.includes("praktykant")) enrichedExp = "intern";
  }

  return {
    external_id: `pracuj_${raw.offerId}`,
    platform: "pracuj.pl",
    title: nd.jobTitle || raw.title || "Unknown",
    company: nd.companyName || raw.company || "Unknown",
    url: cleanUrl,
    salary_min: sal.min,
    salary_max: sal.max,
    currency: "PLN",
    contract_type: enrichedContractType,
    location: nd.displayWorkplace || parseRegion(raw.region),
    remote: enrichedRemote,
    city: nd.displayWorkplace || "",
    skills: skillsFromAi.length > 0 ? skillsFromAi : [],
    category: "",
    experience_level: enrichedExp,
    description: description,
    discovered_at: new Date().toISOString(),
    published_at: nd.lastPublicated || null,
    salary_period: sal.period,
    hybrid: enrichedHybrid,
    _raw: raw._raw ?? [],
  };
}

// ——————————————————————————————————————————————————————————————————————————
//  Main
// ——————————————————————————————————————————————————————————————————————————

async function main() {
  const scraper = new PracujScraper({ maxPages: MAX_PAGES });
  const result = await scraper.scrape();
  writeOutput("pracuj", result.jobs);
  log.info(`Wrote ${result.jobs.length} jobs`);
  printTopJobs("[Pracuj]", result.jobs);
  return result;
}

module.exports = {
  metadata: {
    id: "pracuj",
    name: "Pracuj.pl",
    capabilities: ["browser"],
    needsBrowser: true,
    platform: "pracuj.pl",
    configFields: {
      max_pages: {
        type: "number",
        label: "Max Pages",
        description: "Maximum number of pagination pages to scrape",
        default: 2,
        min: 1,
        max: 100,
        unit: "pages",
      },
      request_delay_ms: {
        type: "number",
        label: "Request Delay (ms)",
        description: "Milliseconds to wait between requests (politeness delay)",
        default: 500,
        min: 0,
        max: 10000,
        step: 100,
        unit: "ms",
      },
      detail_concurrency: {
        type: "number",
        label: "Detail Concurrency",
        description: "Number of concurrent detail page fetches",
        default: 5,
        min: 1,
        max: 20,
        unit: "requests",
      },
      max_enrich_jobs: {
        type: "number",
        label: "Max Enrich Jobs",
        description: "Maximum number of jobs to enrich per run",
        default: 200,
        min: 10,
        max: 1000,
        unit: "jobs",
      },
    },
  },
  main,
  register(registry) {
    registry.register(this);
  },
};
if (require.main === module) main().catch(err => { console.error("[Pracuj] Unhandled rejection:", err); process.exit(1); });
