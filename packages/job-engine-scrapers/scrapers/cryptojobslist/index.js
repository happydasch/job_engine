#!/usr/bin/env node
/**
 * CryptoJobsList Scraper — fetch-based (public RSS feed).
 *
 * The cryptojobslist.com HTML pages sit behind a Cloudflare challenge, but the
 * site publishes its newest ~100 jobs at https://api.cryptojobslist.com/jobs.rss
 * (cryptojobslist.com/rss redirects there). Each <item> carries:
 *   title, link, dc:creator (company), media:location, description (full HTML,
 *   starting with a "Tags: …" line of category links).
 * The feed has no salary or publish date.
 */

const cheerio = require("cheerio");
const log = require("@job-engine-scrapers/core").logger("cryptojobslist");
const { fetchResult } = require("@job-engine-scrapers/core").fetch;
const { writeOutput, printTopJobs, saveRawData } = require("@job-engine-scrapers/core").output;
const { deduplicateByKey, sortBySalary } = require("@job-engine-scrapers/core").dedup;
const { getTagSet, matchesAnyTag } = require("@job-engine-scrapers/core").tags;
const { extractSkills } = require("@job-engine-scrapers/core").skills;

const FEED_URL = "https://api.cryptojobslist.com/jobs.rss";
const BLOCKCHAIN_WORDS = ["defi", "web3", "blockchain", "ethereum", "bitcoin", "solidity", "crypto"];

const TAG_SET = getTagSet();

// ——————————————————————————————————————————————————————————————————————————
//  Parse RSS items
// ——————————————————————————————————————————————————————————————————————————

function parseFeed(xml) {
  const $ = cheerio.load(xml, { xmlMode: true });
  return $("item").map((_, el) => {
    const it = $(el);
    const $desc = cheerio.load(it.find("description").text());
    // First <p> is "Tags: <a>Web3 Jobs</a> • <a>…</a>" — the hrefs carry the slugs.
    const tagLinks = $desc("p").first().find("a")
      .map((__, a) => ($desc(a).attr("href") || "").split("/").pop())
      .get()
      .filter(Boolean);
    $desc("p").first().remove();
    $desc("p, li, br, h1, h2, h3, h4").after(" "); // keep block boundaries in .text()
    return {
      title: it.find("title").first().text().trim(),
      url: it.find("link").first().text().trim(),
      company: it.find("dc\\:creator").text().trim(),
      location: it.find("media\\:location").text().trim(),
      tags: tagLinks,
      description: $desc.root().text().replace(/\s+/g, " ").trim(),
    };
  }).get();
}

// ——————————————————————————————————————————————————————————————————————————
//  Map feed items to JobOffer
// ——————————————————————————————————————————————————————————————————————————

function mapItems(items, rawPath) {
  const jobs = [];
  for (const j of items) {
    if (!j.title || !j.url) continue;
    const slug = j.url.split("/").pop();

    const rawText = `${j.title} ${j.tags.join(" ")} ${j.description}`;
    const techStack = extractSkills(rawText);
    if (!matchesAnyTag(TAG_SET, rawText.toLowerCase()) && techStack.length === 0) continue;

    const location = j.location || "Remote";
    jobs.push({
      external_id: `cryptojobslist_${slug}`,
      platform: "cryptojobslist.com",
      title: j.title,
      company: j.company || "Unknown",
      url: j.url,
      salary_min: null,
      salary_max: null,
      currency: "USD",
      contract_type: "B2B",
      location,
      remote: /remote|anywhere/i.test(location) || !j.location,
      skills: techStack,
      category: j.tags.some((t) => BLOCKCHAIN_WORDS.includes(t)) ? "blockchain" : "",
      experience_level: "",
      requirements: j.description.slice(0, 5000),
      discovered_at: new Date().toISOString(),
      nice_to_have_skills: "[]",
      languages: "[]",
      published_at: null,
      expired_at: null,
      last_published_at: null,
      working_time: "full_time",
      latitude: null,
      longitude: null,
      street: "",
      _raw: rawPath ? [rawPath] : [],
    });
  }
  return jobs;
}

// ——————————————————————————————————————————————————————————————————————————
//  Main
// ——————————————————————————————————————————————————————————————————————————

async function main() {
  log.info(`Fetching ${FEED_URL}…`);
  const result = await fetchResult(FEED_URL, { headers: { Accept: "application/rss+xml" } });
  if (!result.ok) {
    throw new Error(`[cryptojobslist] HTTP ${result.status}${result.error ? `: ${result.error}` : ""} — ${FEED_URL}`);
  }

  const rawPath = saveRawData("cryptojobslist", "feed", result.body, "html");
  const items = parseFeed(result.body);
  if (items.length === 0) {
    throw new Error("[cryptojobslist] RSS feed contained no <item> entries — feed format may have changed");
  }
  log.info(`Found ${items.length} jobs in RSS feed`);

  const matches = sortBySalary(deduplicateByKey(mapItems(items, rawPath), (j) => j.external_id));
  writeOutput("cryptojobslist", matches);

  log.info(`→ ${matches.length} matching offers`);
  printTopJobs("[CryptoJobsList]", matches);

  return { platform: "cryptojobslist.com", count: matches.length, jobs: matches };
}

module.exports = {
  metadata: {
    id: "cryptojobslist",
    name: "CryptoJobsList",
    capabilities: ["fetch"],
    needsBrowser: false,
    platform: "cryptojobslist.com",
  },
  main,
  parseFeed,
  register(registry) {
    registry.register(this);
  },
};
if (require.main === module) main().catch(err => { console.error("[CryptoJobsList] Unhandled rejection:", err); process.exit(1); });
