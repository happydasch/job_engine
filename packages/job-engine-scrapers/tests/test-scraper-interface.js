#!/usr/bin/env node
/**
 * Tests for scraper-interface.js — validateScraperModule, validateJobOffer, JOB_OFFER_SCHEMA.
 */

const assert = require("node:assert");
const { describe, it } = require("node:test");

const {
  validateScraperModule,
  validateJobOffer,
  JOB_OFFER_SCHEMA,
} = require("../core/scraper-interface");

const {
  SAMPLE_JOB_FULL,
  SAMPLE_JOB_MINIMAL,
  SAMPLE_JOB_MISSING_REQUIRED,
} = require("./helpers/fixtures");

// ─── validateScraperModule ──────────────────────────────────────────────

describe("validateScraperModule", () => {
  it("returns true for a valid module", () => {
    const mod = {
      metadata: { id: "test", name: "Test" },
      main: async () => {},
      register: () => {},
    };
    assert.ok(validateScraperModule(mod));
  });

  it("returns false for null/undefined", () => {
    assert.equal(validateScraperModule(null), false);
    assert.equal(validateScraperModule(undefined), false);
    assert.equal(validateScraperModule("string"), false);
  });

  it("returns false when metadata is missing", () => {
    assert.equal(
      validateScraperModule({ main: async () => {}, register: () => {} }),
      false
    );
  });

  it("returns false when metadata.id is missing", () => {
    assert.equal(
      validateScraperModule({
        metadata: { name: "Test" },
        main: async () => {},
        register: () => {},
      }),
      false
    );
  });

  it("returns false when metadata.name is missing", () => {
    assert.equal(
      validateScraperModule({
        metadata: { id: "test" },
        main: async () => {},
        register: () => {},
      }),
      false
    );
  });

  it("returns false when main is missing", () => {
    assert.equal(
      validateScraperModule({
        metadata: { id: "test", name: "Test" },
        register: () => {},
      }),
      false
    );
  });

  it("returns false when register is missing", () => {
    assert.equal(
      validateScraperModule({
        metadata: { id: "test", name: "Test" },
        main: async () => {},
      }),
      false
    );
  });

  it("returns false when main is not a function", () => {
    assert.equal(
      validateScraperModule({
        metadata: { id: "test", name: "Test" },
        main: "not a function",
        register: () => {},
      }),
      false
    );
  });
});

// ─── validateJobOffer ───────────────────────────────────────────────────

describe("validateJobOffer", () => {
  it("returns true for a valid full job", () => {
    assert.ok(validateJobOffer(SAMPLE_JOB_FULL, "test"));
  });

  it("returns true for a minimal valid job (required fields only)", () => {
    assert.ok(validateJobOffer(SAMPLE_JOB_MINIMAL, "test"));
  });

  it("returns false for a job missing required fields", () => {
    assert.equal(
      validateJobOffer(SAMPLE_JOB_MISSING_REQUIRED, "test"),
      false
    );
  });

  it("returns false for null/undefined job", () => {
    assert.equal(validateJobOffer(null, "test"), false);
    assert.equal(validateJobOffer(undefined, "test"), false);
  });

  it("returns false when external_id is empty string", () => {
    assert.equal(
      validateJobOffer(
        {
          external_id: "",
          platform: "test",
          title: "Test",
          company: "TestCo",
          url: "https://example.com",
        },
        "test"
      ),
      false
    );
  });

  it("returns false when advisory mode is off and job is missing required fields", () => {
    assert.equal(
      validateJobOffer(SAMPLE_JOB_MISSING_REQUIRED, "test", {
        advisory: false,
      }),
      false
    );
  });

  it("returns true for a valid job with advisory mode off", () => {
    assert.ok(validateJobOffer(SAMPLE_JOB_FULL, "test", { advisory: false }));
  });
});

// ─── JOB_OFFER_SCHEMA ───────────────────────────────────────────────────

describe("JOB_OFFER_SCHEMA", () => {
  it("has the correct structure", () => {
    assert.equal(JOB_OFFER_SCHEMA.type, "object");
    assert.ok(Array.isArray(JOB_OFFER_SCHEMA.required));
    assert.ok(JOB_OFFER_SCHEMA.properties);
  });

  it("lists external_id, platform, title, company, url as required", () => {
    const required = JOB_OFFER_SCHEMA.required;
    assert.ok(required.includes("external_id"));
    assert.ok(required.includes("platform"));
    assert.ok(required.includes("title"));
    assert.ok(required.includes("company"));
    assert.ok(required.includes("url"));
  });

  it("defines salary_min as nullable number", () => {
    const prop = JOB_OFFER_SCHEMA.properties.salary_min;
    assert.ok(prop.type.includes("number"));
    assert.ok(prop.type.includes("null"));
  });

  it("defines skills as array of strings", () => {
    const prop = JOB_OFFER_SCHEMA.properties.skills;
    assert.equal(prop.type, "array");
    assert.equal(prop.items.type, "string");
  });

  it("defines remote as boolean", () => {
    assert.equal(JOB_OFFER_SCHEMA.properties.remote.type, "boolean");
  });
});