#!/usr/bin/env node
/**
 * CryptocurrencyJobs Scraper — fetch-based (static HTML).
 *
 * Fetches https://cryptocurrencyjobs.co/engineering/ and parses job listing
 * cards using cheerio. Each card contains a job title, company, tags, and
 * a link to the full posting.
 *
 * Single-page scraper (no pagination).
 */

const log = require("@job-engine-scrapers/core").logger("cryptocurrencyjobs");
const proxy = require("@job-engine-scrapers/core").proxy;
const { fetchHtml } = require("@job-engine-scrapers/core").fetch;
const { writeOutput, printTopJobs, saveRawData } = require("@job-engine-scrapers/core").output;
const { deduplicateByKey, sortBySalary, stableId } = require("@job-engine-scrapers/core").dedup;
const { getTagSet, matchesAnyTag } = require("@job-engine-scrapers/core").tags;
const cheerio = require("cheerio");
const config = require("@job-engine-scrapers/core").config;

const BASE_URL = "https://cryptocurrencyjobs.co";
const PAGE_URL = BASE_URL + "/engineering/";

const TAGS = config.getTags();
const TAG_SET = getTagSet();

// ——————————————————————————————————————————————————————————————————————————
//  Parse HTML job cards
// ——————————————————————————————————————————————————————————————————————————

function parseJobs(html, rawPath) {
  const $ = cheerio.load(html);
  const jobs = [];

  // Each job listing is a direct child <li> of the <ul> with class "mt-6"
  // The job card contains: logo img, title link, company link, tag links, date
  $("ul.mt-6 > li").each((_, el) => {
    // Title: <a> inside the <h2>
    const titleLink = $(el).find("h2 a").first();
    const title = titleLink.text().trim();
    const href = titleLink.attr("href");
    if (!title || !href) return;

    const url = href.startsWith("http") ? href : BASE_URL + (href.startsWith("/") ? "" : "/") + href;

    // Company: <h3> text
    const companyEl = $(el).find("h3").first();
    const company = companyEl.text().trim() || "Unknown";

    // Tags: all <a> tags with href patterns — skip title, company, and logo links
    const tags = [];
    $(el).find("a[href]").each((_, tagEl) => {
      const tagHref = $(tagEl).attr("href") || "";
      const tagName = $(tagEl).text().trim();
      if (tagHref === href) return; // skip title link
      if (tagHref.startsWith("/startups/")) return; // company link
      if (tagHref.startsWith("http")) return; // logo link or external
      // Skip non-technical category/role/type links
      if (tagHref.startsWith("/engineering/")) return;
      if (tagHref.startsWith("/full-time/")) return;
      if (tagHref.startsWith("/part-time/")) return;
      if (tagHref.startsWith("/contract/")) return;
      if (tagHref.startsWith("/freelance/")) return;
      if (tagHref.startsWith("/other/")) return;
      if (!tagName) return;
      tags.push(tagName);
    });

    // Extract slug from URL for external_id
    const slugMatch = url.match(/\/engineering\/([^/?#]+)/);
    const slug = slugMatch ? slugMatch[1] : stableId(url);
    const externalId = `cryptocurrencyjobs_${slug}`;

    const allText = (title + " " + company + " " + tags.join(" ")).toLowerCase();
    const matchesTag = matchesAnyTag(TAG_SET, allText);

    // Extract skills from title, company, and tags
    const skills = [];
    if (matchesTag) {
      // Use tag names as skills
      for (const tag of tags) {
        if (!["full-time", "full time", "part-time", "part time", "remote", "featured"].includes(tag.toLowerCase())) {
          skills.push(tag);
        }
      }
    }

    // Remote status — many crypto jobs are remote; check title/tags
    const isRemote = allText.includes("remote") || allText.includes("worldwide");

    jobs.push({
      external_id: externalId,
      platform: "cryptocurrencyjobs",
      title,
      company,
      url,
      salary_min: null,
      salary_max: null,
      currency: "USD",
      contract_type: "",
      location: isRemote ? "Remote" : "",
      remote: isRemote,
      skills: [...new Set(skills)],
      category: "blockchain",
      experience_level: "",
      requirements: "",
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
  });

  return jobs;
}

// ——————————————————————————————————————————————————————————————————————————
//  Main
// ——————————————————————————————————————————————————————————————————————————

async function main() {
  log.info(`Fetching ${PAGE_URL}…`);
  const html = await fetchHtml(PAGE_URL, "[CryptocurrencyJobs]");
  if (!html) {
    log.warn("No HTML received");
    writeOutput("cryptocurrencyjobs", []);
    return { platform: "cryptocurrencyjobs", count: 0, jobs: [] };
  }

  // Save raw HTML response
  const rawPath = saveRawData("cryptocurrencyjobs", "page_0", html, "html");
  if (rawPath) {
    log.info(`Saved raw data: ${rawPath}`);
  }

  if (html.includes("Cloudflare") || html.includes("Just a moment")) {
    log.warn("Blocked by WAF");
    writeOutput("cryptocurrencyjobs", []);
    return { platform: "cryptocurrencyjobs", count: 0, jobs: [] };
  }

  const jobs = parseJobs(html, rawPath);
  log.info(`Found ${jobs.length} jobs`);

  // Deduplicate + sort + write
  const matches = sortBySalary(deduplicateByKey(jobs, (j) => j.external_id));
  writeOutput("cryptocurrencyjobs", matches);

  log.info(`→ ${matches.length} matching offers`);
  printTopJobs("[CryptocurrencyJobs]", matches);

  return { platform: "cryptocurrencyjobs", count: matches.length, jobs: matches };
}

module.exports = {
  metadata: {
    id: "cryptocurrencyjobs",
    name: "CryptocurrencyJobs",
    capabilities: ["fetch"],
    needsBrowser: false,
    platform: "cryptocurrencyjobs",
  },
  main,
  register(registry) {
    registry.register(this);
  },
};
if (require.main === module) main().catch((err) => { console.error("[CryptocurrencyJobs] Fatal:", err); process.exit(1); });
