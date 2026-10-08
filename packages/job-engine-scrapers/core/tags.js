#!/usr/bin/env node
/**
 * Shared Tag Matching — getTagSet(), matchesAnyTag().
 *
 * Consolidates the `const TAG_SET = new Set(TAGS.map(t => t.toLowerCase()))`
 * pattern that is duplicated in every scraper file.
 *
 * Usage:
 *   const { getTagSet, matchesAnyTag } = require("./core/tags");
 *   const tagSet = getTagSet();
 *   if (matchesAnyTag(tagSet, "python engineer")) { ... }
 */

const config = require("./config");

/**
 * Get the shared tag set from config, cached as a Set.
 * @returns {Set<string>}
 */
function getTagSet() {
  const tags = config.getTags();
  return new Set(tags.map((t) => t.toLowerCase()));
}

// Escape regex metacharacters so tags like "c++", "node.js", "c#" match literally.
function escapeRegex(str) {
  return str.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

// Memoize the compiled matcher per tag set (avoids rebuilding on every job).
const _regexCache = new WeakMap();

function _getTagRegex(tagSet) {
  let re = _regexCache.get(tagSet);
  if (re) return re;

  const alternatives = [...tagSet]
    .filter(Boolean)
    .sort((a, b) => b.length - a.length) // longest-first so "react native" wins over "react"
    .map(escapeRegex)
    .join("|");

  // Whole-token match: the tag must not be flanked by alphanumerics, so "ai"
  // matches "ai engineer" but NOT "email" / "brain". Metachars in tags (++, #,
  // .) are literal and unaffected by the alphanumeric boundary guards.
  re = alternatives
    ? new RegExp(`(?<![a-z0-9])(?:${alternatives})(?![a-z0-9])`, "i")
    : /(?!)/; // never matches when there are no tags
  _regexCache.set(tagSet, re);
  return re;
}

/**
 * Check if any tag from the set appears in the search text as a whole token.
 *
 * Uses word-boundary matching (not naive substring) to avoid false positives
 * like the tag "ai" matching "email" or "go" matching "google".
 *
 * @param {Set<string>} tagSet
 * @param {string} searchText — lowercased text to search
 * @returns {boolean}
 */
function matchesAnyTag(tagSet, searchText) {
  if (!searchText) return false;
  return _getTagRegex(tagSet).test(searchText);
}

module.exports = { getTagSet, matchesAnyTag };