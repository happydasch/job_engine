#!/usr/bin/env node
/**
 * Unified Skills Regex + Normalizer — single source of truth for skill keyword
 * extraction and normalization.
 *
 * @deprecated Use the Python TaxonomyResolver (job_engine.taxonomy) as the canonical
 * synonym registry.  This JS file is kept for backward compatibility with scrapers
 * that rely on normalizeSkills() for format cleaning.  The SKILLS_REGEX map is
 * mirrored in packages/job-engine-core/src/job_engine/taxonomy.py (SEED_ALIASES).
 *
 * Consolidates the 6+ independent copies of SKILLS_REGEX that exist across
 * scrapers. Contains ALL terms from every variant,
 * so no matches are lost when scrapers use different versions.
 *
 * normalizeSkills() strips non-letter characters from skill names, keeping only
 * letters, digits, and whitespace (single spaces). Underscores are converted to
 * spaces first so that regex-matched terms like `machine_learning` become
 * `machine learning`. This ensures consistent, human-readable skill names
 * across all scrapers — API-rich scrapers often return skills with
 * punctuation, numbers, or mixed case. Original casing is preserved;
 * case-insensitive comparison is handled by the scoring engine at query time.
 *
 * Usage:
 *   const { extractSkills, normalizeSkills } = require("./core/skills");
 *   const skills = extractSkills("Python + FastAPI + Docker");
 *   // → ["Python", "FastAPI", "Docker"]
 *
 *   const clean = normalizeSkills(["Python3", "C++", "Machine Learning"]);
 *   // → ["Python3", "C", "Machine Learning"]
 */

// Unified regex combining all terms from all scraper variants
const SKILLS_REGEX =
  /\b(python|fastapi|pydantic|asyncio|celery|websockets|pytest|postgresql|sqlalchemy|alembic|sql|asyncpg|mongodb|redis|cassandra|elasticsearch|pandas|numpy|scikit-learn|tensorflow|pytorch|langchain|llm|plotly|dash|matplotlib|streamlit|docker|aws|lambda|github_actions|trading|fintech|machine_learning|ai|react|typescript|javascript|node|go|rust|graphql|kubernetes|django|flask|terraform|google\s*cloud|azure|api|bot|telegram|discord|web\s*scraping|backtesting|quantitative|solidity|web3|ethereum|bitcoin|defi|blockchain|smart_contracts|data_science|devops|full_stack|backend|nosql)\b/gi;

/**
 * Normalize a single skill string: keep only letters, digits, and whitespace,
 * then collapse whitespace. Underscores are converted to spaces first so that
 * regex-matched terms like `machine_learning` become `machine learning`.
 * Strips punctuation and special characters while preserving original casing
 * and word boundaries.
 *
 * @param {string} skill — raw skill name
 * @returns {string} — normalized skill name
 */
function normalizeSkill(skill) {
  return skill
    // Casing is preserved — case-insensitive comparison is handled by the
    // scoring engine at query time via normalize_skill().
    .replace(/_/g, " ")               // underscores → spaces first
    // Replace any character that is NOT a letter, digit, or space with a space.
    // This way c++ → "c  " → "c", node.js → "node  js" → "node js",
    // .net → " net" → "net", kat. b → "kat  b" → "kat b".
    .replace(/[^\p{L}\p{N}\s]/gu, " ")
    .replace(/\s+/g, " ")             // collapse whitespace to single space
    .trim();
}

/**
 * Normalize an array of skill strings: keep only letters and words
 * (separated by spaces), deduplicate, and filter out empty results.
 *
 * @param {string[]} skills — array of raw skill names
 * @returns {string[]} — unique normalized skill names
 */
function normalizeSkills(skills) {
  if (!Array.isArray(skills) || skills.length === 0) return [];
  return [...new Set(
    skills
      .filter((s) => typeof s === "string" && s.trim())
      .map(normalizeSkill)
      .filter(Boolean)
  )];
}

/**
 * Extract deduplicated skill keywords from text, then normalize them.
 *
 * @param {string} text — raw text to search
 * @returns {string[]} — unique normalized skill terms
 */
function extractSkills(text) {
  if (!text) return [];
  const matches = text.match(SKILLS_REGEX) || [];
  return normalizeSkills(matches);
}

module.exports = { SKILLS_REGEX, extractSkills, normalizeSkills, normalizeSkill };