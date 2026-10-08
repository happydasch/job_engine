#!/usr/bin/env node
/**
 * Scraper Interface Contract — JSDoc typedefs + validation utilities.
 *
 * This file defines the interface every scraper module must satisfy.
 * It is documentation-first: the JSDoc types serve as the type system.
 *
 * A valid scraper module exports:
 *   - `metadata`  (ScraperMetadata)
 *   - `main`      (async function that scrapes and writes output)
 *   - `register`  (function that takes a ScraperRegistry)
 *
 * @module scraper-interface
 */

/**
 * @typedef {Object} ConfigFieldDef
 * @property {string}     type       - Field type: "number" | "string" | "boolean" | "select" | "password"
 * @property {string}     label      - Human-readable field label
 * @property {string}     [description] - Help text shown below the field
 * @property {boolean}    [required=false] - Whether the field must have a value
 * @property {number|string|boolean|null} [default] - Default value
 * @property {number}     [min]      - Minimum value (number fields)
 * @property {number}     [max]      - Maximum value (number fields)
 * @property {number}     [step]     - Step increment (number fields)
 * @property {string}     [placeholder] - Placeholder text (string fields)
 * @property {Array<{label:string, value:string}>} [options] - Options for select fields
 * @property {string}     [unit]     - Unit suffix (e.g. "pages", "minutes")
 */

/**
 * @typedef {Object} ScraperMetadata
 * @property {string}   id             - Platform ID (matches scraper_config.yaml key, e.g. "justjoin_it")
 * @property {string}   name           - Human-readable display name (e.g. "JustJoin.it")
 * @property {string}   [version]      - Scraper version string (optional)
 * @property {('browser'|'api'|'fetch'|'rss')[]} [capabilities] - Fetch methods this scraper uses
 * @property {boolean}  [needsBrowser=false] - Whether this scraper requires Playwright
 * @property {Object<string, ConfigFieldDef>} [configFields] - Schema describing scraper config fields
 */

/**
 * @typedef {Object} JobOffer
 *
 * ## Required Fields (must be non-empty, or job is dropped by writeOutput())
 * @property {string}        external_id - Platform-unique ID, e.g. `justjoin_<guid>`
 * @property {string}        platform   - Source platform name, e.g. `justjoin.it`, `nofluffjobs`
 * @property {string}        title      - Job title from the listing
 * @property {string}        company    - Company name (resolved to Company entity on import)
 * @property {string}        url        - Direct link to the job posting
 *
 * ## Scoring-Critical Fields (strongly recommended; missing degrades match scores)
 * @property {number|null}   salary_min      - Minimum / from salary
 * @property {number|null}   salary_max      - Maximum / to salary
 * @property {string}        currency        - ISO-ish code: USD, EUR, GBP, PLN
 * @property {string}        contract_type   - B2B, PERMANENT, UoP, UZ, UD, full_time, part_time, contract, freelance, internship, other
 * @property {string}        location        - Human-readable location (city, region, or "Remote")
 * @property {boolean}       remote          - Whether the role is fully remote
 * @property {string[]}      skills          - Skill keyword list
 * @property {string}        category        - Job category key (e.g. python, blockchain, data)
 * @property {string}        experience_level - Seniority label (e.g. junior, mid, senior, trainee)
 * @property {string}        description     - Full job description text (canonical name; `requirements` maps here)
 * @property {string}        discovered_at   - ISO timestamp of discovery
 *
 * ## Optional Enrichment Fields (populated by richer scrapers)
 * @property {string}        [nice_to_have_skills] - JSON array of nice-to-have skill strings
 * @property {string}        [languages]           - JSON array of {code, level} or {name, level} objects
 * @property {string|null}   [published_at]        - ISO timestamp of original publication
 * @property {string|null}   [expired_at]          - ISO timestamp of expiry
 * @property {string|null}   [last_published_at]   - ISO timestamp of last re-publication
 * @property {string}        [working_time]        - full_time, part_time, or flexible
 * @property {number|null}   [latitude]            - Geographic latitude
 * @property {number|null}   [longitude]           - Geographic longitude
 * @property {string}        [street]              - Street address
 *
 * ## Extended Fields (beyond standard JobOffer — set by specific scrapers)
 * @property {string}        [benefits]            - JSON array of benefit strings (nfj, solidjobs)
 * @property {boolean}       [hybrid]              - Whether the role is hybrid (pracuj, solidjobs)
 * @property {string}        [city]                - City from location data (solidjobs)
 * @property {string}        [division]            - Division/category detail (solidjobs)
 * @property {string}        [body]                - Short description body (nfj)
 * @property {string}        [company_url]         - Company website URL (nfj)
 * @property {string}        [company_logo_url]    - Company logo URL (solidjobs)
 * @property {number|null}   [secondary_salary_min]       - Min for alternative contract (solidjobs)
 * @property {number|null}   [secondary_salary_max]       - Max for alternative contract (solidjobs)
 * @property {string}        [secondary_currency]         - Currency for alternative contract (solidjobs)
 * @property {string}        [secondary_contract_type]    - Label for alternative contract (solidjobs)
 * @property {string|null}   [valid_from]         - ISO datetime when posting becomes valid (solidjobs)
 * @property {string|null}   [valid_to]           - ISO datetime when posting expires (solidjobs)
 *
 * ## Raw Data References (paths to saved raw HTML/API responses)
 * @property {string[]}      [_raw]               - Paths to raw data files relative to data/scraper-output/
 */

/**
 * A valid scraper module.
 *
 * @typedef {Object} ScraperModule
 * @property {ScraperMetadata} metadata
 * @property {() => Promise<void>|Promise<Object[]>} main - Main scrape function
 * @property {(registry: import('./registry')) => void} register - Self-registration hook
 */

// ── Validation ──────────────────────────────────────────────────────────────

/**
 * Check that an object conforms to ScraperModule.
 * Logs warnings for missing/invalid fields but does not throw (graceful).
 *
 * @param {Object} mod - The module object to validate
 * @returns {boolean} True if the module is valid
 */
function validateScraperModule(mod) {
  if (!mod || typeof mod !== "object") {
    console.warn("[scraper-interface] Invalid module: not an object");
    return false;
  }

  if (!mod.metadata || typeof mod.metadata !== "object") {
    console.warn("[scraper-interface] Missing or invalid metadata");
    return false;
  }

  const m = mod.metadata;
  if (!m.id || typeof m.id !== "string") {
    console.warn("[scraper-interface] metadata.id is required (string)");
    return false;
  }
  if (!m.name || typeof m.name !== "string") {
    console.warn("[scraper-interface] metadata.name is required (string)");
    return false;
  }
  if (typeof mod.main !== "function") {
    console.warn(`[scraper-interface] Scraper "${m.id}" is missing main() function`);
    return false;
  }

  if (typeof mod.register !== "function") {
    console.warn(`[scraper-interface] Scraper "${m.id}" is missing register() function`);
    return false;
  }

  return true;
}

/**
 * Validate a JobOffer object, logging warnings for missing required fields.
 * Checks the most important fields to catch schema drift early.
 *
 * @param {Object} job - Raw job object to validate
 * @param {string} [source] - Platform identifier for log context
 * @param {object} [opts]
 * @param {boolean} [opts.advisory=true] - Log advisory warnings for optional fields
 * @param {boolean} [opts.checkTypes=false] - Also run schema type-checking on populated fields
 * @returns {boolean} True if job passes basic validation
 */
function validateJobOffer(job, source, opts = {}) {
  const { advisory = true, checkTypes = false } = opts;
  const prefix = source ? `[${source}]` : "[job]";
  const required = ["external_id", "platform", "title", "company", "url"];
  let valid = true;

  for (const field of required) {
    if (!job || !job[field] || (typeof job[field] === "string" && job[field].trim() === "")) {
      if (advisory) console.warn(`${prefix} Missing required field "${field}"`);
      valid = false;
    }
  }

  // Warn about suspicious missing optional fields that matter for scoring.
  // Advisory-only (does not affect validity); pass { advisory: false } to run
  // this as a silent required-fields gate (e.g. per-job filtering in writeOutput).
  if (advisory && job) {
    const important = ["salary_min", "salary_max", "skills", "remote"];
    for (const field of important) {
      if (job[field] === undefined || job[field] === null) {
        console.warn(`${prefix} Missing "${field}" — scoring may be degraded`);
      }
    }
  }

  // Schema type-checking: warn when a populated field has the wrong type.
  // This is opt-in (checkTypes: true) to avoid overhead in hot paths.
  if (checkTypes && job && valid) {
    const schema = JOB_OFFER_SCHEMA.properties;
    for (const [field, fieldSchema] of Object.entries(schema)) {
      const val = job[field];
      if (val === undefined || val === null) continue;
      const expectedTypes = Array.isArray(fieldSchema.type) ? fieldSchema.type : [fieldSchema.type];
      const actualType = Array.isArray(val) ? "array" : typeof val;
      if (!expectedTypes.includes(actualType) && actualType !== "null") {
        console.warn(`${prefix} Field "${field}" expected ${expectedTypes.join("|")}, got ${actualType} (${typeof val})`);
      }
    }
  }

  return valid;
}

// ── JSON Schema for JobOffer ───────────────────────────────────────────────

/**
 * JSON Schema for a JobOffer object.
 * Used for runtime validation in validateJobOffer().
 */
const JOB_OFFER_SCHEMA = {
  type: "object",
  required: ["external_id", "platform", "title", "company", "url"],
  properties: {
    // -- Required fields --
    external_id: { type: "string", description: "Platform-unique ID" },
    platform: { type: "string", description: "Source platform name" },
    title: { type: "string", description: "Job title" },
    company: { type: "string", description: "Company name" },
    url: { type: "string", description: "Job posting URL" },

    // -- Scoring-critical --
    salary_min: { type: ["number", "null"], description: "Minimum / from salary" },
    salary_max: { type: ["number", "null"], description: "Maximum / to salary" },
    currency: { type: "string", description: "Currency code (USD, EUR, GBP, PLN)" },
    contract_type: { type: "string", description: "Contract type (B2B, PERMANENT, UoP, etc.)" },
    location: { type: "string", description: "Job location (city, region, or Remote)" },
    remote: { type: "boolean", description: "Whether the role is fully remote" },
    skills: { type: "array", items: { type: "string" }, description: "Skill keyword list" },
    category: { type: "string", description: "Job category key" },
    experience_level: { type: "string", description: "Seniority label" },
    description: { type: "string", description: "Full job description text" },
    discovered_at: { type: "string", description: "ISO timestamp of discovery" },

    // -- Optional enrichment --
    nice_to_have_skills: { type: "string", description: "JSON array of nice-to-have skill strings" },
    languages: { type: "string", description: "JSON array of language objects" },
    published_at: { type: ["string", "null"], description: "ISO timestamp of publication" },
    expired_at: { type: ["string", "null"], description: "ISO timestamp of expiry" },
    last_published_at: { type: ["string", "null"], description: "ISO timestamp of last publication" },
    working_time: { type: "string", description: "Work schedule (full_time, part_time, flexible)" },
    latitude: { type: ["number", "null"], description: "Geographic latitude" },
    longitude: { type: ["number", "null"], description: "Geographic longitude" },
    street: { type: "string", description: "Street address" },

    // -- Extended fields --
    benefits: { type: "string", description: "JSON array of benefit strings" },
    hybrid: { type: "boolean", description: "Whether the role is hybrid" },
    city: { type: "string", description: "City from location data" },
    division: { type: "string", description: "Division/category detail" },
    body: { type: "string", description: "Short description body" },
    company_url: { type: "string", description: "Company website URL" },
    company_logo_url: { type: "string", description: "Company logo URL" },
    secondary_salary_min: { type: ["number", "null"], description: "Min for alternative contract" },
    secondary_salary_max: { type: ["number", "null"], description: "Max for alternative contract" },
    secondary_currency: { type: "string", description: "Currency for alternative contract" },
    secondary_contract_type: { type: "string", description: "Label for alternative contract" },
    valid_from: { type: ["string", "null"], description: "ISO posting valid-from datetime" },
    valid_to: { type: ["string", "null"], description: "ISO posting valid-to datetime" },

    // -- Raw data refs --
    _raw: { type: "array", items: { type: "string" }, description: "Paths to raw data files" },
  },
};

module.exports = { validateScraperModule, validateJobOffer, JOB_OFFER_SCHEMA };