#!/usr/bin/env node
/**
 * ScraperRegistry — singleton registry where scrapers self-register.
 *
 * Usage:
 *   const registry = require('./registry');
 *   // Scrapers call this during load:
 *   //   registry.register(module);
 *   // Consumers use:
 *   //   registry.getAll()    → all registered ScraperModules
 *   //   registry.get('id')  → a specific ScraperModule
 *   //   registry.getActive() → ScraperModules whose scraper is enabled in config
 *
 * @module registry
 */

const { validateScraperModule } = require('./scraper-interface');

class ScraperRegistry {
  constructor() {
    /** @type {Map<string, Object>} id → ScraperModule */
    this._scrapers = new Map();
  }

  /**
   * Register a scraper module. Called by scrapers during require().
   * Validates the module before registering and warns on duplicates.
   *
   * @param {Object} mod - A valid ScraperModule ({ metadata, main, register? })
   * @returns {boolean} True if registration succeeded
   */
  register(mod) {
    if (!validateScraperModule(mod)) {
      console.warn(`[registry] Refusing to register invalid module`);
      return false;
    }

    const id = mod.metadata.id;

    if (this._scrapers.has(id)) {
      console.warn(`[registry] Duplicate registration for "${id}" — overwriting`);
    }

    this._scrapers.set(id, mod);
    return true;
  }

  /**
   * Get a scraper by scraper ID.
   *
   * @param {string} id - Scraper ID (e.g. "justjoin_it")
   * @returns {Object|undefined} The ScraperModule, or undefined
   */
  get(id) {
    return this._scrapers.get(id);
  }

  /**
   * All registered scrapers.
   *
   * @returns {Object[]} Array of ScraperModules
   */
  getAll() {
    return Array.from(this._scrapers.values());
  }

  /**
   * Get scrapers whose scraper is enabled in config.
   * Requires config.js to be loaded first.
   *
   * @returns {Object[]} Array of active ScraperModules
   */
  getActive() {
    const config = require('./config');
    const activeIds = new Set(config.getActiveScrapers().map(p => p.id));
    return this.getAll().filter(mod => activeIds.has(mod.metadata.id));
  }

  /**
   * IDs of scrapers that need Playwright.
   *
   * @returns {Set<string>}
   */
  getBrowserIds() {
    const ids = new Set();
    for (const mod of this._scrapers.values()) {
      if (mod.metadata.needsBrowser) {
        ids.add(mod.metadata.id);
      }
    }
    return ids;
  }

  /**
   * Return all metadata as a plain array — consumed by the Python dashboard.
   *
   * @returns {Array<{id: string, name: string, capabilities: string[], needsBrowser: boolean}>}
   */
  getMetadata() {
    return this.getAll().map(mod => ({
      id: mod.metadata.id,
      name: mod.metadata.name,
      version: mod.metadata.version,
      platform: mod.metadata.platform || null,
      capabilities: mod.metadata.capabilities || [],
      needsBrowser: mod.metadata.needsBrowser || false,
      configFields: mod.metadata.configFields || null,
    }));
  }

  /**
   * Number of registered scrapers.
   *
   * @returns {number}
   */
  get size() {
    return this._scrapers.size;
  }

  /**
   * Check if a scraper is registered.
   *
   * @param {string} id
   * @returns {boolean}
   */
  has(id) {
    return this._scrapers.has(id);
  }
}

// Singleton
const registry = new ScraperRegistry();
// Also export the class so tests can create isolated instances
registry.ScraperRegistry = ScraperRegistry;
module.exports = registry;