# Security Policy

## Untrusted Posting Data

Job postings come from third-party platforms and are **untrusted by default**.

### Prompt Injection Protection

- Every LLM prompt template **must** include the `{SANITIZE_FORBIDDANCE}` placeholder, which is populated by the sanitisation module (`job_engine/_sanitize.py`).
- Raw job posting text is passed through `sanitize_job_posting()` before reaching any prompt template. This function strips embedded instructions, control characters, and known prompt-injection patterns.
- Profile and CV content (first-party data) flows through separate, injection-sanitised template slots.

### URL Fetching from Postings

The engine **never** follows URLs extracted from job posting content. Scraped offer URLs are used only as identifiers and links for the user; automated fetching from embedded links in descriptions is forbidden.

The contributor rules for handling this data are in [docs/rules.md](docs/rules.md#untrusted-data-discipline).

## Reporting a Vulnerability

Please **do not open a public issue** for security problems. Report them privately via
GitHub's [private vulnerability reporting](https://github.com/happydasch/job-engine/security/advisories/new)
(Security tab → "Report a vulnerability"). Include steps to reproduce and the affected version
(see `VERSION`). You should get a response within a week.

In scope: prompt-injection bypasses of the sanitisation logic, path traversal or file access
outside the data directory, unsafe deserialisation, and anything that leaks profile/CV data.

Out of scope: issues that require exposing the dashboard to an untrusted network — Job Engine
is local-only by design and has no authentication (see the README).
