#!/usr/bin/env node
/**
 * @job-engine-scrapers/core — barrel that re-exports all shared scraper utilities.
 *
 * @module @job-engine-scrapers/core
 */

const registry = require('./registry');
const scraperInterface = require('./scraper-interface');
const fetch = require('./fetch');
const salary = require('./salary');
const skills = require('./skills');
const tags = require('./tags');
const dedup = require('./dedup');
const output = require('./output');
const logger = require('./logger');
const stealth = require('./stealth');
const proxy = require('./proxy');
const config = require('./config');
const catalogs = require('./catalogs');
const BrowserScraper = require('./browserScraper');

module.exports = {
  registry,
  scraperInterface,
  fetch,
  salary,
  skills,
  tags,
  dedup,
  output,
  logger,
  stealth,
  proxy,
  config,
  catalogs,
  browserScraper: BrowserScraper,
};
