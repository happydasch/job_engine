#!/usr/bin/env node
/**
 * Tests for the RSS/Atom feed parsers of the reddit and cryptojobslist scrapers.
 */

const assert = require("node:assert");
const { describe, it } = require("node:test");

const reddit = require("../../scrapers/reddit/index");
const cryptojobslist = require("../../scrapers/cryptojobslist/index");

const REDDIT_ATOM = `<?xml version="1.0" encoding="UTF-8"?><feed xmlns="http://www.w3.org/2005/Atom">
<entry><author><name>/u/acme_hr</name></author><category term="forhire" label="r/forhire"/>
<content type="html">&lt;div class=&quot;md&quot;&gt;&lt;p&gt;Need a Python dev.&lt;/p&gt;&lt;p&gt;Remote, $50/h.&lt;/p&gt;&lt;/div&gt;</content>
<id>t3_abc123</id><link href="https://www.reddit.com/r/forhire/comments/abc123/hiring_python/"/>
<updated>2026-10-08T04:49:43+00:00</updated><published>2026-10-08T04:49:43+00:00</published>
<title>[Hiring] Python developer</title></entry></feed>`;

const CJL_RSS = `<?xml version="1.0" encoding="UTF-8"?><rss xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:media="http://search.yahoo.com/mrss/" version="2.0"><channel>
<item><title><![CDATA[Senior Solidity Engineer]]></title>
<description><![CDATA[<p>Tags: <a href="https://cryptojobslist.com/web3">Web3 Jobs</a> • <a href="https://cryptojobslist.com/solidity">Solidity Jobs</a><p><strong>About:</strong></p><p>Build DeFi.</p>]]></description>
<link>https://cryptojobslist.com/jobs/senior-solidity-engineer-at-acme</link>
<dc:creator><![CDATA[Acme]]></dc:creator><media:location>Remote</media:location></item>
</channel></rss>`;

describe("reddit — parseFeed", () => {
  it("extracts id, title, author, url, date and readable body", () => {
    const [p] = reddit.parseFeed(REDDIT_ATOM);
    assert.equal(p.id, "t3_abc123");
    assert.equal(p.subreddit, "forhire");
    assert.equal(p.title, "[Hiring] Python developer");
    assert.equal(p.author, "acme_hr");
    assert.equal(p.url, "https://www.reddit.com/r/forhire/comments/abc123/hiring_python/");
    assert.equal(p.published, "2026-10-08T04:49:43+00:00");
    assert.equal(p.body, "Need a Python dev. Remote, $50/h.");
  });
});

describe("cryptojobslist — parseFeed", () => {
  it("extracts title, company, location, tag slugs and description", () => {
    const [j] = cryptojobslist.parseFeed(CJL_RSS);
    assert.equal(j.title, "Senior Solidity Engineer");
    assert.equal(j.url, "https://cryptojobslist.com/jobs/senior-solidity-engineer-at-acme");
    assert.equal(j.company, "Acme");
    assert.equal(j.location, "Remote");
    assert.deepEqual(j.tags, ["web3", "solidity"]);
    assert.equal(j.description, "About: Build DeFi.");
  });
});
