#!/usr/bin/env node
/**
 * Reddit Scraper — reads r/forhire, r/remotejs, r/algotrading for matching jobs.
 *
 * Uses the public Atom feed of a combined multireddit
 * (`/r/forhire+remotejs+algotrading/new/.rss`). old.reddit.com now sits behind a
 * login wall and the JSON API requires OAuth, but feeds stay public. Anonymous
 * access is limited to ~1 request/minute, so everything is fetched in ONE request
 * (newest 100 posts) and filtered locally for "[hiring]" posts matching the
 * profile tags. Reddit rejects spoofed browser User-Agents from non-browser
 * clients, so a descriptive one is sent as Reddit's API rules ask.
 */

const cheerio = require("cheerio");
const { fetchResult } = require("@job-engine-scrapers/core").fetch;
const { writeOutput, printTopJobs, saveRawData } = require("@job-engine-scrapers/core").output;
const { deduplicateByKey } = require("@job-engine-scrapers/core").dedup;
const { getTagSet, matchesAnyTag } = require("@job-engine-scrapers/core").tags;
const { extractSkills } = require("@job-engine-scrapers/core").skills;
const log = require("@job-engine-scrapers/core").logger("reddit");

const SUBREDDITS = ["forhire", "remotejs", "algotrading"];
const MAX_AGE_MS = 30 * 24 * 60 * 60 * 1000;
const FEED_URL = `https://www.reddit.com/r/${SUBREDDITS.join("+")}/new/.rss?limit=100`;
const USER_AGENT = "job-engine-scrapers/1.0 (job feed reader)";

const TAG_SET = getTagSet();

/** Parse Atom entries into plain post objects. */
function parseFeed(xml) {
  const $ = cheerio.load(xml, { xmlMode: true });
  return $("entry").map((_, el) => {
    const e = $(el);
    const $body = cheerio.load(e.find("content").text());
    $body("p, li, br, h1, h2, h3, h4").after(" "); // keep block boundaries in .text()
    return {
      id: e.find("id").first().text().trim(),
      subreddit: e.find("category").attr("term") || "",
      title: e.find("title").first().text().trim(),
      author: e.find("author > name").text().trim().replace(/^\/u\//, ""),
      url: e.find("link").attr("href") || "",
      published: e.find("published").text().trim() || e.find("updated").text().trim(),
      body: $body.root().text().replace(/\s+/g, " ").trim(),
    };
  }).get();
}

function toJob(p, subreddit, rawPath) {
  const text = `${p.title} ${p.body}`;
  return {
    external_id: `reddit_${subreddit}_${p.id}`,
    platform: "reddit.com",
    title: p.title,
    company: p.author ? `u/${p.author}` : "Unknown",
    url: p.url,
    salary_min: null,
    salary_max: null,
    currency: "USD",
    contract_type: "B2B",
    location: "Remote",
    remote: true,
    skills: extractSkills(text),
    category: subreddit,
    experience_level: "",
    requirements: p.body.slice(0, 2000),
    discovered_at: new Date().toISOString(),
    nice_to_have_skills: "[]",
    languages: "[]",
    published_at: p.published || null,
    expired_at: null,
    last_published_at: null,
    working_time: "full_time",
    latitude: null,
    longitude: null,
    street: "",
    _raw: rawPath ? [rawPath] : [],
  };
}

// ─── Main ───────────────────────────────────────────────────────────────

async function main() {
  const cutoff = Date.now() - MAX_AGE_MS;

  log.info(`Fetching ${FEED_URL}…`);
  const result = await fetchResult(FEED_URL, {
    headers: { Accept: "application/atom+xml", "User-Agent": USER_AGENT },
  });
  if (!result.ok) {
    throw new Error(`[reddit] HTTP ${result.status}${result.error ? `: ${result.error}` : ""} — ${FEED_URL}`);
  }

  const rawPath = saveRawData("reddit", "feed", result.body, "html");
  const posts = parseFeed(result.body);
  const jobs = posts
    .filter((p) => p.title && p.id && p.url)
    .filter((p) => p.title.toLowerCase().includes("[hiring]"))
    .filter((p) => !p.published || Date.parse(p.published) >= cutoff)
    .filter((p) => matchesAnyTag(TAG_SET, `${p.title} ${p.body}`.toLowerCase()))
    .map((p) => toJob(p, p.subreddit, rawPath));
  log.info(`${posts.length} posts → ${jobs.length} matching [hiring] posts`);

  const matches = deduplicateByKey(jobs, (j) => j.external_id);
  writeOutput("reddit", matches);
  log.info(`→ ${matches.length} matching offers`);
  printTopJobs("[reddit]", matches);

  return { platform: "reddit.com", count: matches.length, jobs: matches };
}

if (require.main === module) {
  main().catch((err) => {
    console.error("[reddit] Fatal:", err);
    process.exit(1);
  });
}

module.exports = {
  metadata: {
    id: "reddit",
    name: "Reddit",
    capabilities: ["fetch"],
    needsBrowser: false,
    platform: "reddit.com",
    configFields: {
      timeout_seconds: {
        type: "number",
        label: "Timeout (seconds)",
        description: "Maximum time per scraper run before timeout (0 = use global default)",
        default: 0,
        min: 0,
        max: 600,
        step: 10,
        unit: "seconds",
      },
    },
  },
  main,
  parseFeed,

  register(registry) {
    registry.register(this);
  },
};
