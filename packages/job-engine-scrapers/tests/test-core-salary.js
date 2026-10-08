#!/usr/bin/env node
/**
 * Tests for core/salary.js — parseSalaryRange, parseJsonLDSalary,
 * parseHourlyRate, parseHourlyRateToYearly, detectPeriod, detectCurrency.
 */

const assert = require("node:assert");
const { describe, it } = require("node:test");

const {
  parseSalaryRange,
  parseJsonLDSalary,
  parseHourlyRate,
  parseHourlyRateToYearly,
  detectPeriod,
  detectCurrency,
} = require("../core/salary");

// ─── detectCurrency ──────────────────────────────────────────────────────

describe("detectCurrency", () => {
  it("detects USD from $ symbol", () => {
    assert.equal(detectCurrency("$100k"), "USD");
  });

  it("detects USD from usd keyword", () => {
    assert.equal(detectCurrency("1000 USD"), "USD");
  });

  it("detects GBP from £ symbol", () => {
    assert.equal(detectCurrency("£75k"), "GBP");
  });

  it("detects GBP from gbp keyword", () => {
    assert.equal(detectCurrency("75000 GBP"), "GBP");
  });

  it("detects EUR from € symbol", () => {
    assert.equal(detectCurrency("€50k"), "EUR");
  });

  it("detects EUR from eur keyword", () => {
    assert.equal(detectCurrency("50000 EUR"), "EUR");
  });

  it("detects PLN from zł suffix", () => {
    assert.equal(detectCurrency("25000 zł"), "PLN");
  });

  it("detects PLN from pln keyword", () => {
    assert.equal(detectCurrency("25000 PLN"), "PLN");
  });

  it("returns null for unknown currency", () => {
    assert.equal(detectCurrency("100 CHF"), null);
  });

  it("returns null for empty string", () => {
    assert.equal(detectCurrency(""), null);
  });
});

// ─── parseSalaryRange ─────────────────────────────────────────────────────

describe("parseSalaryRange", () => {
  it("returns nulls for empty input", () => {
    const r = parseSalaryRange("");
    assert.equal(r.salary_min, null);
    assert.equal(r.salary_max, null);
    assert.equal(r.currency, null);
  });

  it("returns nulls for null input", () => {
    const r = parseSalaryRange(null);
    assert.equal(r.salary_min, null);
    assert.equal(r.salary_max, null);
    assert.equal(r.currency, null);
  });

  it("parses $100k - $200k range", () => {
    const r = parseSalaryRange("$100k - $200k");
    assert.equal(r.salary_min, 100000);
    assert.equal(r.salary_max, 200000);
    assert.equal(r.currency, "USD");
  });

  it("parses $100k - $200k (hyphen) range", () => {
    const r = parseSalaryRange("$100k - $200k");
    assert.equal(r.salary_min, 100000);
    assert.equal(r.salary_max, 200000);
    assert.equal(r.currency, "USD");
  });

  it("parses $100k to $200k range", () => {
    const r = parseSalaryRange("$100k to $200k");
    assert.equal(r.salary_min, 100000);
    assert.equal(r.salary_max, 200000);
    assert.equal(r.currency, "USD");
  });

  it("parses £75k - £120k range (GBP)", () => {
    const r = parseSalaryRange("£75k - £120k");
    assert.equal(r.salary_min, 75000);
    assert.equal(r.salary_max, 120000);
    assert.equal(r.currency, "GBP");
  });

  it("parses €50k - €80k range (EUR)", () => {
    const r = parseSalaryRange("€50k - €80k");
    assert.equal(r.salary_min, 50000);
    assert.equal(r.salary_max, 80000);
    assert.equal(r.currency, "EUR");
  });

  it("parses 10000 - 20000 PLN range", () => {
    const r = parseSalaryRange("10000 - 20000 PLN");
    assert.equal(r.salary_min, 10000);
    assert.equal(r.salary_max, 20000);
    assert.equal(r.currency, "PLN");
  });

  it("parses 10000 zł - 20000 zł range (zł suffix)", () => {
    const r = parseSalaryRange("10000 zł - 20000 zł");
    assert.equal(r.salary_min, 10000);
    assert.equal(r.salary_max, 20000);
    assert.equal(r.currency, "PLN");
  });

  it("parses $100,000 - $200,000 with commas", () => {
    const r = parseSalaryRange("$100,000 - $200,000");
    assert.equal(r.salary_min, 100000);
    assert.equal(r.salary_max, 200000);
    assert.equal(r.currency, "USD");
  });

  it("parses single k-suffixed value", () => {
    const r = parseSalaryRange("$120k");
    assert.equal(r.salary_min, 120000);
    assert.equal(r.salary_max, 120000);
    assert.equal(r.currency, "USD");
  });

  it("parses single value with no k suffix but has currency context", () => {
    const r = parseSalaryRange("50000 USD");
    assert.equal(r.salary_min, 50000);
    assert.equal(r.salary_max, 50000);
    assert.equal(r.currency, "USD");
  });

  it("does NOT parse a bare number without currency context", () => {
    const r = parseSalaryRange("5+ years experience");
    assert.equal(r.salary_min, null);
    assert.equal(r.salary_max, null);
    assert.equal(r.currency, null);
  });

  it("does NOT parse empty text with symbols", () => {
    const r = parseSalaryRange("Competitive");
    assert.equal(r.salary_min, null);
    assert.equal(r.salary_max, null);
    assert.equal(r.currency, null);
  });
});

// ─── parseHourlyRate ─────────────────────────────────────────────────────

describe("parseHourlyRate", () => {
  it("parses $50 - $75/hr range", () => {
    const r = parseHourlyRate("$50 - $75/hr");
    assert.equal(r.salary_min, 50);
    assert.equal(r.salary_max, 75);
  });

  it("parses $30 - $50/hr (en-dash)", () => {
    const r = parseHourlyRate("$30 - $50/hr");
    assert.equal(r.salary_min, 30);
    assert.equal(r.salary_max, 50);
  });

  it("parses Fixed Price", () => {
    const r = parseHourlyRate("Fixed Price: $5000");
    assert.equal(r.salary_min, null);
    assert.equal(r.salary_max, 5000);
  });

  it("returns nulls for empty", () => {
    const r = parseHourlyRate("");
    assert.equal(r.salary_min, null);
    assert.equal(r.salary_max, null);
  });
});

// ─── parseHourlyRateToYearly ───────────────────────────────────────────────

describe("parseHourlyRateToYearly", () => {
  it("converts $50 - $75/hr to yearly (×2080)", () => {
    const r = parseHourlyRateToYearly("$50 - $75/hr");
    assert.equal(r.salary_min, 50 * 2080);
    assert.equal(r.salary_max, 75 * 2080);
  });

  it("returns nulls for no match", () => {
    const r = parseHourlyRateToYearly("No rate here");
    assert.equal(r.salary_min, null);
    assert.equal(r.salary_max, null);
  });
});

// ─── parseJsonLDSalary ────────────────────────────────────────────────────

describe("parseJsonLDSalary", () => {
  it("parses a simple JobPosting with baseSalary", () => {
    const jsonld = JSON.stringify({
      "@type": "JobPosting",
      baseSalary: {
        value: {
          value: 120000,
          currency: "USD",
          unitText: "YEAR",
        },
      },
    });
    const r = parseJsonLDSalary(jsonld);
    assert.equal(r.salary_min, 120000);
    assert.equal(r.salary_max, 120000);
    assert.equal(r.currency, "USD");
  });

  it("parses a range with minValue/maxValue", () => {
    const jsonld = JSON.stringify({
      "@type": "JobPosting",
      baseSalary: {
        value: {
          minValue: 100000,
          maxValue: 150000,
          currency: "USD",
          unitText: "YEAR",
        },
      },
    });
    const r = parseJsonLDSalary(jsonld);
    assert.equal(r.salary_min, 100000);
    assert.equal(r.salary_max, 150000);
    assert.equal(r.currency, "USD");
  });

  it("converts MONTH unit to yearly", () => {
    const jsonld = JSON.stringify({
      "@type": "JobPosting",
      baseSalary: {
        value: {
          minValue: 8333,
          maxValue: 12500,
          currency: "USD",
          unitText: "MONTH",
        },
      },
    });
    const r = parseJsonLDSalary(jsonld);
    assert.equal(r.salary_min, 8333 * 12);
    assert.equal(r.salary_max, 12500 * 12);
  });

  it("parses @graph-wrapped JobPosting", () => {
    const jsonld = JSON.stringify({
      "@graph": [
        { "@type": "WebPage" },
        {
          "@type": "JobPosting",
          baseSalary: {
            value: {
              value: "90000",
              currency: "EUR",
              unitText: "YEAR",
            },
          },
        },
      ],
    });
    const r = parseJsonLDSalary(jsonld);
    assert.equal(r.salary_min, 90000);
    assert.equal(r.currency, "EUR");
  });

  it("returns USD defaults for missing salary data", () => {
    const r = parseJsonLDSalary('{"@type": "WebPage"}');
    assert.equal(r.salary_min, null);
    assert.equal(r.salary_max, null);
    assert.equal(r.currency, "USD");
  });

  it("returns USD defaults for unparseable JSON", () => {
    const r = parseJsonLDSalary("not json");
    assert.equal(r.salary_min, null);
    assert.equal(r.salary_max, null);
    assert.equal(r.currency, "USD");
  });

  it("returns USD defaults for empty string", () => {
    const r = parseJsonLDSalary("");
    assert.equal(r.salary_min, null);
    assert.equal(r.salary_max, null);
    assert.equal(r.currency, "USD");
  });
});

// ─── detectPeriod ──────────────────────────────────────────────────────────

describe("detectPeriod", () => {
  it("detects hour/godz", () => {
    assert.equal(detectPeriod("per hour"), "hour");
    assert.equal(detectPeriod("na godzinę"), "hour");
  });

  it("detects month/mies", () => {
    assert.equal(detectPeriod("per month"), "month");
    assert.equal(detectPeriod("miesięcznie"), "month");
  });

  it("detects year/rok", () => {
    assert.equal(detectPeriod("per year"), "year");
    assert.equal(detectPeriod("na rok"), "year");
  });

  it("returns null for null/empty", () => {
    assert.equal(detectPeriod(null), null);
    assert.equal(detectPeriod(""), null);
  });

  it("returns null for unknown string", () => {
    assert.equal(detectPeriod("once"), null);
  });
});