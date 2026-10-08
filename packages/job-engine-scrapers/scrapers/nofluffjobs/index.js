#!/usr/bin/env node
/**
 * NoFluffJobs Scraper — public JSON API (search + posting detail).
 *
 * NFJ exposes an unauthenticated REST API that the site's own frontend calls.
 * We use it directly instead of scraping the SSR HTML `serverApp-state` blob:
 * no Cloudflare challenge, no proxy rotation needed, and the data is already
 * structured JSON.
 *
 *   Search : POST /api/search/posting?pageTo=N&pageSize=20&region=pl
 *            Content-Type: application/infiniteSearch+json
 *            body: {"rawSearch": "<free text>"}
 *            → { totalCount, totalPages, postings: [ {id,name,title,salary,…} ] }
 *
 *   Detail : GET  /api/posting/{id}
 *            → { requirements:{musts,nices,description,languages}, company,
 *                specs:{dailyTasks}, benefits, essentials, … }
 *
 * One search per boosted keyword from my_profile.yaml. Remote-only profiles
 * append "remote" to the search text (NFJ ranks fullyRemote offers first for it).
 * Search postings carry title/tech/salary/location but NOT the skill lists, so
 * each tag-matched posting is enriched via the detail endpoint (bounded by
 * MAX_DETAIL_FETCHES to keep a broad search from exploding into thousands of
 * requests).
 *
 * Job links use the posting's `id` slug: /pl/job/{id}.
 *
 * Contract types on NFJ are per-salary-entry. `salary` may be a single object
 * or an array (B2B, UoP, …); pickBestSalary() prefers B2B, then highest upper
 * bound.
 */

const { fetchJson } = require("@job-engine-scrapers/core").fetch;
const proxy = require("@job-engine-scrapers/core").proxy;
const log = require("@job-engine-scrapers/core").logger("nofluffjobs");
const { writeOutput, printTopJobs, saveRawData } = require("@job-engine-scrapers/core").output;
const { deduplicateByKey, sortBySalary } = require("@job-engine-scrapers/core").dedup;
const { getTagSet, matchesAnyTag } = require("@job-engine-scrapers/core").tags;
const stealth = require("@job-engine-scrapers/core").stealth;
const config = require("@job-engine-scrapers/core").config;

const BASE = "https://nofluffjobs.com";
const SEARCH_API = `${BASE}/api/search/posting`;
const detailApi = (id) => `${BASE}/api/posting/${encodeURIComponent(id)}`;

const SEARCH_TERMS = config.getSearchTerms();
const REMOTE_ONLY = config.getRemoteOnly();
const TAG_SET = getTagSet();
const SCRAPER_CFG = config.getScraper("nofluffjobs");
const MAX_PAGES = SCRAPER_CFG ? SCRAPER_CFG.max_pages : 5;
const REGION = (SCRAPER_CFG && SCRAPER_CFG.region) || "pl";

// NFJ paginates loosely: `pageTo=1` returns the whole first (exact-match) block
// in one response, and `pageSize` acts as a soft cap on that block rather than a
// strict per-page count. Asking for a higher `pageTo` selects a later slice that
// is empty for small result sets — so we always fetch pageTo=1 and size the
// block off max_pages (~20 postings per notional page).
const PAGE_SIZE = MAX_PAGES * 20;

// The detail endpoint is public and un-throttled, so we enrich every matched
// posting rather than sampling — but through a small concurrency pool so a
// broad keyword doesn't open hundreds of sockets at once. DETAIL_CONCURRENCY
// requests are in flight at a time; MAX_DETAIL_FETCHES is a safety backstop
// against a pathologically broad run.
const DETAIL_CONCURRENCY = 6;
const MAX_DETAIL_FETCHES = 400;

// NFJ's own frontend sends this content type on the search POST; some WAF rules
// key on it, so we mirror it exactly.
const SEARCH_CONTENT_TYPE = "application/infiniteSearch+json";

// ─── Salary contract type ordering (prefer B2B → UoP → …) ────────────────────

const CONTRACT_PREFERENCE = ["b2b", "uop", "uod", "mandate"];

/**
 * Pick the best salary entry from a posting's salary array (or single object).
 * NoFluffJobs returns salary as either a single object or an array of entries
 * per contract type.
 *
 * @param {object|object[]} salary
 * @returns {{ from: number|null, to: number|null, currency: string, type: string }|null}
 */
function pickBestSalary(salary) {
  if (!salary) return null;
  const entries = Array.isArray(salary) ? salary : [salary];
  if (entries.length === 0) return null;

  const scored = entries
    .filter((e) => e && e.to)
    .map((e) => ({
      ...e,
      prefIdx: CONTRACT_PREFERENCE.indexOf((e.type || "").toLowerCase()),
    }));

  if (scored.length === 0) {
    // Fallback: first entry even without a salary_to bound.
    return {
      from: entries[0].from ?? null,
      to: entries[0].to ?? null,
      currency: entries[0].currency ?? "PLN",
      type: entries[0].type ?? "unknown",
    };
  }

  scored.sort((a, b) => {
    const aPref = a.prefIdx >= 0 ? a.prefIdx : 999;
    const bPref = b.prefIdx >= 0 ? b.prefIdx : 999;
    if (aPref !== bPref) return aPref - bPref; // preferred contract first
    return (b.to ?? 0) - (a.to ?? 0); // then highest upper bound
  });

  return {
    from: scored[0].from ?? null,
    to: scored[0].to ?? null,
    currency: scored[0].currency ?? "PLN",
    type: scored[0].type ?? "unknown",
  };
}

// ——————————————————————————————————————————————————————————————————————————
//  API access
// ——————————————————————————————————————————————————————————————————————————

/**
 * Run one keyword search against the JSON API and return its raw postings.
 * `pageTo=MAX_PAGES` asks the API for up to that many pages in a single
 * response (NFJ returns the whole exact-match block at once, so one request
 * per term is enough).
 */
async function searchTerm(term) {
  const rawSearch = term.replace(/_/g, " ") + (REMOTE_ONLY ? " remote" : "");
  const url =
    `${SEARCH_API}?pageTo=1&pageSize=${PAGE_SIZE}` +
    `&salaryCurrency=PLN&salaryPeriod=month&region=${encodeURIComponent(REGION)}`;

  const data = await fetchJson(
    url,
    {
      method: "POST",
      headers: { "Content-Type": SEARCH_CONTENT_TYPE },
      body: JSON.stringify({ rawSearch }),
      maxRetries: 2,
    },
    "[NoFluffJobs]",
  );

  if (!data || !Array.isArray(data.postings)) {
    log.warn(`No postings for "${term}"`);
    return [];
  }

  // Save raw search API response
  const searchId = `search_${term.replace(/[^a-zA-Z0-9]/g, "_")}`;
  const rawPath = saveRawData("nofluffjobs", searchId, data, "json");
  if (rawPath) {
    log.info(`Saved raw search data: ${rawPath}`);
  }

  log.info(
    `"${term}": ${data.postings.length} postings (total ${data.totalCount ?? "?"})`,
  );

  // Attach raw path to each posting
  const postings = data.postings.map((p) => {
    if (rawPath) p._raw = [rawPath];
    return p;
  });
  return postings;
}

/**
 * Fetch a posting's detail record and pull out the skill lists and description
 * that the search endpoint omits. Returns null on any failure — the caller
 * falls back to the search-only fields.
 */
async function fetchDetail(id) {
  const data = await fetchJson(detailApi(id), { maxRetries: 1 }, "[NoFluffJobs]");
  if (!data) return null;

  // Save raw detail API response
  const rawPath = saveRawData("nofluffjobs", `detail_${id}`, data, "json");

  const req = data.requirements || {};
  const pluck = (arr) =>
    Array.isArray(arr) ? arr.map((x) => x && x.value).filter(Boolean) : [];

  return {
    musts: pluck(req.musts),
    nices: pluck(req.nices),
    description: typeof req.description === "string" ? req.description : "",
    languages: Array.isArray(req.languages)
      ? req.languages
          .map((l) => (l.code ? `${l.code}${l.level ? ` (${l.level})` : ""}` : null))
          .filter(Boolean)
      : [],
    dailyTasks: Array.isArray(data.specs?.dailyTasks) ? data.specs.dailyTasks : [],
    category: data.basics?.category || "",
    // companyUrl is a site-relative path ("/company/acme-abc123"); make absolute.
    companyUrl: data.companyUrl ? `${BASE}${data.companyUrl}` : null,
    _raw: rawPath ? [rawPath] : [],
  };
}

/**
 * Map an async worker over items with a bounded number of concurrent calls.
 * Preserves input order in the result array.
 */
async function mapConcurrent(items, limit, worker) {
  const results = new Array(items.length);
  let next = 0;
  async function run() {
    while (next < items.length) {
      const i = next++;
      results[i] = await worker(items[i], i);
    }
  }
  await Promise.all(Array.from({ length: Math.min(limit, items.length) }, run));
  return results;
}

// ——————————————————————————————————————————————————————————————————————————
//  Filtering & normalization
// ——————————————————————————————————————————————————————————————————————————

/** Cheap tag match on search-listing fields (before the detail fetch). */
function matchesTag(posting) {
  const searchText = [
    posting.title,
    posting.technology,
    posting.category,
    ...(posting.flavors ?? []),
    ...(posting.seniority ?? []),
  ]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
  return matchesAnyTag(TAG_SET, searchText);
}

/**
 * Normalise a search posting (+ optional detail record) into our JobOffer
 * schema. `detail` may be null when the enrichment request failed or the
 * per-run detail budget was exhausted.
 */
function normalizePosting(p, detail) {
  // ── Location ────────────────────────────────────────────────────────
  const places = p.location?.places ?? [];
  const cityNames = places.map((pl) => pl.city).filter(Boolean);
  const remote =
    p.location?.fullyRemote === true ||
    p.fullyRemote === true ||
    cityNames.some((c) => c.toLowerCase() === "remote");
  const realCities = [...new Set(cityNames.filter((c) => c.toLowerCase() !== "remote"))];
  let location;
  if (realCities.length > 0) {
    location = realCities.join(", ");
  } else if (remote) {
    location = "Remote";
  } else if (Array.isArray(p.regions) && p.regions.length > 0) {
    location = p.regions
      .map((r) => (typeof r === "string" ? r.toUpperCase() : r?.name))
      .filter(Boolean)
      .join(", ");
  } else {
    location = "Unknown";
  }

  // ── Salary ──────────────────────────────────────────────────────────
  const salary = pickBestSalary(p.salary);
  const contractType = salary?.type?.toUpperCase() ?? "B2B";

  // ── Skills: prefer detail "musts", fall back to listing tech/flavors ──
  const techStack = (
    detail?.musts?.length
      ? detail.musts
      : [...(p.flavors ?? []), p.technology].filter(Boolean)
  );

  const niceToHave = detail?.nices ?? [];
  const languages = detail?.languages ?? [];

  // ── Requirements text: strip HTML from the detail description, then
  //    append daily tasks so the skill-scorer sees the full picture. ──
  let requirements = "";
  if (detail?.description) {
    requirements = detail.description.replace(/<[^>]*>/g, " ").replace(/\s+/g, " ").trim();
  }
  if (detail?.dailyTasks?.length) {
    requirements = `${requirements}\nTasks: ${detail.dailyTasks.join("; ")}`.trim();
  }

  // ── Experience level ────────────────────────────────────────────────
  const experienceParts = [...(p.seniority ?? [])];
  if (p.positionLevel && !experienceParts.includes(p.positionLevel)) {
    experienceParts.push(p.positionLevel);
  }

  // NFJ returns the same posting as separate search entries per region
  // (16 voivodeships + Remote), each with a unique `id` but a shared
  // canonical `reference` code. Use `reference` for dedup so multi-city
  // or fully-remote jobs produce one DB record instead of 17.
  const canonicalId = p.reference || p.id;
  const jobId = `nfj_${canonicalId}`;

  return {
    external_id: jobId,
    platform: "nofluffjobs.com",
    title: p.title ?? "Unknown",
    company: p.name ?? "Unknown",
    // p.id is the canonical URL slug used by NFJ's own job links.
    url: `${BASE}/pl/job/${p.id}`,
    salary_min: salary?.from ?? null,
    salary_max: salary?.to ?? null,
    currency: salary?.currency ?? "PLN",
    contract_type: contractType,
    location,
    remote,
    skills: techStack,
    category: detail?.category || p.category || "",
    experience_level: experienceParts.join(", "),
    requirements,
    body: requirements ? requirements.slice(0, 5000) : "",
    discovered_at: new Date().toISOString(),
    nice_to_have_skills: JSON.stringify(niceToHave.slice(0, 30)),
    languages: JSON.stringify(languages.slice(0, 10)),
    working_time: "full_time",
    // p.posted is a ms epoch — normalise to ISO like the other scrapers.
    published_at:
      typeof p.posted === "number" ? new Date(p.posted).toISOString() : (p.posted ?? null),
    company_url: detail?.companyUrl ?? null,
    benefits: [],

    // ─── Raw data refs ─────────────────────────────────────────
    _raw: [...(p._raw ?? []), ...(detail?._raw ?? [])],
  };
}

// ——————————————————————————————————————————————————————————————————————————
//  Main
// ——————————————————————————————————————————————————————————————————————————

async function main() {
  log.info(
    `Starting API scrape (${SEARCH_TERMS.length} terms, region ${REGION}, up to ${MAX_PAGES} pages${REMOTE_ONLY ? ", remote-only" : ""})`,
  );

  // 1. Collect postings across all search terms, deduped by NFJ id and
  //    canonical reference. NFJ returns the same posting once per region
  //    (voivodeship), each with a different `id` but the same `reference`.
  const seenIds = new Set();
  const seenRefs = new Set();
  const postings = [];
  for (let i = 0; i < SEARCH_TERMS.length; i++) {
    const found = await searchTerm(SEARCH_TERMS[i]);
    let added = 0;
    for (const p of found) {
      if (!p?.id || seenIds.has(p.id)) continue;
      seenIds.add(p.id);
      // Dedup by canonical reference: if we already collected a region
      // variant of this job, skip the others.
      if (p.reference && seenRefs.has(p.reference)) continue;
      if (p.reference) seenRefs.add(p.reference);
      postings.push(p);
      added++;
    }
    log.info(
      `"${SEARCH_TERMS[i]}": +${added} new (${postings.length} total unique)`,
    );
    if (i < SEARCH_TERMS.length - 1) await stealth.humanDelay();
  }
  log.info(`Fetched ${postings.length} unique postings from search API`);

  // 2. Tag-match on cheap listing fields before spending detail requests.
  const matched = postings.filter(matchesTag);
  log.info(`  → ${matched.length} tag-matched postings`);

  // 3. Enrich matched postings via the detail endpoint (bounded concurrency).
  const toEnrich = matched.slice(0, MAX_DETAIL_FETCHES);
  if (matched.length > MAX_DETAIL_FETCHES) {
    log.info(
      `safety cap ${MAX_DETAIL_FETCHES} < ${matched.length} matches — ` +
        `${matched.length - MAX_DETAIL_FETCHES} kept with listing data only`,
    );
  }
  log.info(
    `enriching ${toEnrich.length} postings (${DETAIL_CONCURRENCY} concurrent)…`,
  );
  const details = await mapConcurrent(toEnrich, DETAIL_CONCURRENCY, (p) => fetchDetail(p.id));
  const enriched = details.filter(Boolean).length;
  log.info(`  → ${enriched}/${toEnrich.length} enriched with detail data`);

  const jobs = matched.map((p, i) =>
    normalizePosting(p, i < details.length ? details[i] : null),
  );

  // 4. Dedupe + sort + write.
  const out = sortBySalary(deduplicateByKey(jobs, (j) => j.external_id));
  const deduped = jobs.length - out.length;
  if (deduped > 0) log.info(`  → removed ${deduped} duplicates`);

  writeOutput("nofluffjobs", out);
  log.info(`Wrote ${out.length} jobs`);
  printTopJobs("[NoFluffJobs]", out);

  return { platform: "nofluffjobs.com", count: out.length, jobs: out };
}

module.exports = {
  metadata: {
    id: "nofluffjobs",
    name: "NoFluffJobs",
    capabilities: ["fetch"],
    needsBrowser: false,
    platform: "nofluffjobs.com",
    configFields: {
      max_pages: {
        type: "number",
        label: "Max Pages",
        description: "Maximum number of pagination pages to scrape",
        default: 5,
        min: 1,
        max: 100,
        unit: "pages",
      },
    },
  },
  main,
  register(registry) {
    registry.register(this);
  },
};

if (require.main === module) {
  main().catch((err) => {
    console.error("[NoFluffJobs] Fatal:", err);
    process.exit(1);
  });
}
