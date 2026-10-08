#!/usr/bin/env node
/**
 * Shared Salary Parsers — parseSalaryRange(), parseJsonLDSalary(), etc.
 *
 * Consolidates the various ad-hoc salary regex implementations scattered
 * across scrapers into one place with consistent semantics.
 *
 * Usage:
 *   const { parseSalaryRange, parseJsonLDSalary } = require("./core/salary");
 *   const { min, max } = parseSalaryRange("$100k - $200k");
 */

const createLogger = require("./logger");

const log = createLogger("salary");

/**
 * Detect the currency of a salary string.
 *
 * @param {string} str
 * @returns {string|null} — ISO-ish code ("USD"/"GBP"/"EUR"/"PLN") or null
 */
function detectCurrency(str) {
  if (str.includes("$") || /\busd\b/i.test(str)) return "USD";
  if (str.includes("£") || /\bgbp\b/i.test(str)) return "GBP";
  if (str.includes("€") || /\beur\b/i.test(str)) return "EUR";
  if (/\bpln\b|zł/i.test(str)) return "PLN";
  return null;
}

// A number is scaled by 1000 only when it carries an explicit "k"/"K" suffix —
// no more guessing from digit count (which turned "500" into 500000).
function _toAmount(numStr, kSuffix) {
  const val = parseFloat(numStr.replace(/,/g, ""));
  if (Number.isNaN(val)) return null;
  return kSuffix ? val * 1000 : val;
}

/**
 * Normalize a salary string by replacing common currency symbols with
 * a standard prefix, making it easier for regex matching.
 *
 * @param {string} str
 * @returns {string}
 */
function _normalizeCurrencyPrefix(str) {
  // Replace "zł" suffix with "$" prefix so the range regex can match it
  return str.replace(/([\d.,]+)\s*zł/i, "$$$1");
}

/**
 * Parse a string like "$100k - $200k", "1000 - 2000 PLN", "$50 - $75/hr".
 *
 * @param {string} str — raw salary text
 * @returns {{ salary_min: number|null, salary_max: number|null, currency: string|null }}
 */
function parseSalaryRange(str) {
  if (!str) return { salary_min: null, salary_max: null, currency: null };

  const currency = detectCurrency(str);

  // Normalize currency symbols so the regex can match zł suffix as well
  const normalized = _normalizeCurrencyPrefix(str);

  // Match: $100k - $200k or $100,000 - $200,000. Each number may carry its own
  // "k" suffix. The separator is an explicit set of dashes or the word "to"
  // (previously "[--to]+", a char class that also matched stray t/o letters).
  const rangeMatch = normalized.match(
    /[$£€]?\s*(\d[\d,.]*)\s*([kK])?\s*(?:-|-|—|to)\s*[$£€]?\s*(\d[\d,.]*)\s*([kK])?/
  );
  if (rangeMatch) {
    const min = _toAmount(rangeMatch[1], rangeMatch[2]);
    const max = _toAmount(rangeMatch[3], rangeMatch[4]);
    return { salary_min: min, salary_max: max, currency: currency || "USD" };
  }

  // Single value: "$100k" or "100000" or "10000 zł". Only accept a lone number
  // when it carries salary context — a currency (symbol or word) or a "k" suffix.
  // Otherwise a stray digit like the "5" in "5+ years experience" was returned
  // as a salary of 5.
  const singleMatch = normalized.match(/[$£€]?\s*(\d[\d,.]*)\s*([kK])?/);
  if (singleMatch && (currency !== null || singleMatch[2])) {
    const val = _toAmount(singleMatch[1], singleMatch[2]);
    return { salary_min: val, salary_max: val, currency: currency || "USD" };
  }

  return { salary_min: null, salary_max: null, currency };
}

/**
 * Parse a salary from a JSON-LD script block (JobPosting baseSalary).
 *
 * @param {string} jsonldStr — raw JSON-LD script content
 * @returns {{ salary_min: number|null, salary_max: number|null, currency: string }}
 */
function parseJsonLDSalary(jsonldStr) {
  if (!jsonldStr || !jsonldStr.trim()) {
    return { salary_min: null, salary_max: null, currency: "USD" };
  }
  let data;
  try {
    data = JSON.parse(jsonldStr);
  } catch { /* Invalid JSON in salary data */
    const snippet = jsonldStr.replace(/\n/g, " ").trim().slice(0, 120);
    log.warn(`Failed to parse JSON-LD salary data: ${snippet}`);
    return { salary_min: null, salary_max: null, currency: "USD" };
  }
  const graph = data["@graph"] || [data];
  const posting = graph.find(
    (g) => g["@type"] === "JobPosting" || g["@type"] === "JobPostingDetail"
  );
  if (posting && posting.baseSalary) {
    const bs = posting.baseSalary;
    const salaryInfo = Array.isArray(bs) ? bs[0] : bs;
    const value = salaryInfo?.value || salaryInfo;
    if (value) {
      const currency = value.currency || salaryInfo.currency || "USD";
      const unitText = value.unitText || salaryInfo.unitText || "YEAR";
      let minVal = value.minValue ? parseFloat(value.minValue) : null;
      let maxVal = value.maxValue ? parseFloat(value.maxValue) : null;

      if (minVal === null && value.value !== undefined) {
        minVal = parseFloat(value.value);
        maxVal = minVal;
      }

      if (unitText.toUpperCase() === "MONTH" && maxVal) {
        minVal = (minVal || maxVal) * 12;
        maxVal = maxVal * 12;
      }

      return { salary_min: minVal, salary_max: maxVal, currency };
    }
  }
  return { salary_min: null, salary_max: null, currency: "USD" };
}

/**
 * Parse hourly rate like "$50 - $75/hr" or "$50 - $75 per hour".
 *
 * @param {string} text
 * @returns {{ salary_min: number|null, salary_max: number|null }}
 */
function parseHourlyRate(text) {
  const hourly = text.match(/[$£€]?\s*([\d,.]+)\s*[--]\s*[$£€]?\s*([\d,.]+)\s*\/hr/i);
  if (hourly) {
    return {
      salary_min: parseFloat(hourly[1].replace(/,/g, "")),
      salary_max: parseFloat(hourly[2].replace(/,/g, "")),
    };
  }
  const fixed = text.match(/Fixed\s*Price[:\s]*[$£€]?\s*([\d,.]+)/i);
  if (fixed) {
    return { salary_min: null, salary_max: parseFloat(fixed[1].replace(/,/g, "")) };
  }
  return { salary_min: null, salary_max: null };
}

/**
 * Detect salary period from a string.
 *
 * @param {string} str
 * @returns {string|null} — "hour", "month", "year", or null
 */
function detectPeriod(str) {
  if (!str) return null;
  if (/godz|hour/i.test(str)) return "hour";
  if (/mies|month/i.test(str)) return "month";
  if (/rok|year/i.test(str)) return "year";
  return null;
}

/**
 * Parse hourly rate text and convert to yearly (× 2080 hours).
 *
 * @param {string} text — e.g. "$50 - $75/hr" or "$30 - $50 per hour"
 * @returns {{ salary_min: number|null, salary_max: number|null }}
 */
function parseHourlyRateToYearly(text) {
  const rate = parseHourlyRate(text);
  if (rate.salary_min !== null) {
    rate.salary_min = Math.round(rate.salary_min * 2080);
  }
  if (rate.salary_max !== null) {
    rate.salary_max = Math.round(rate.salary_max * 2080);
  }
  return rate;
}

module.exports = {
  parseSalaryRange,
  parseJsonLDSalary,
  parseHourlyRate,
  parseHourlyRateToYearly,
  detectPeriod,
  detectCurrency,
};