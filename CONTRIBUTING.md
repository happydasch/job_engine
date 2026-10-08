# Contributing to Job Engine

Thanks for your interest! Job Engine is a local-first tool, so contributions that keep it simple,
private, and runnable on a single machine are the most welcome.

## Getting started

```bash
cp config/.env.example config/.env
cp examples/my_profile.example.yaml data/my_profile.yaml
make install
make doctor
```

See [DEVELOPMENT.md](DEVELOPMENT.md) for the full project layout and architecture, and
[docs/architecture.md](docs/architecture.md) for the data flow.

## Before you open a PR

Run the full check suite — CI runs the same commands:

```bash
make lint && make typecheck && make test-all
```

Use `make format` to apply ruff formatting (line length 100).

## Project rules

The full rules live in [docs/rules.md](docs/rules.md). The ones reviewers check most:

- **No silent error swallowing or masking fallbacks.** Let exceptions propagate to a caller that
  can handle them; `error`-level logs must be followed by a raise.
- **Untrusted data:** scraped text goes through `sanitize_job_posting()` before any LLM call, and
  every prompt template in `_prompts/` includes `{SANITIZE_FORBIDDANCE}`.
- **Vue:** Composition API with `<script setup>`, scoped styles, reuse `components/common/` and
  `composables/` before creating new ones.
- **Scrapers:** scaffold with `make create-scraper`, read all config from `data/scraper_config.yaml`
  (never `process.env`), declare every option in `metadata.configFields`, and add tests under
  `packages/job-engine-scrapers/tests/`. See
  [CREATING_A_SCRAPER.md](packages/job-engine-scrapers/CREATING_A_SCRAPER.md).
- Respect the [data contract](DATA_CONTRACT.md): never auto-modify user-layer files such as
  `data/my_profile.yaml`.

## Commit messages

[Conventional Commits](https://www.conventionalcommits.org/) with package scopes:

```
feat(core): add X
fix(scrapers): handle rate limiting in linkedin
refactor(dashboard): consolidate Y
feat(scrapers,dashboard): cross-package change
docs: update quickstart
```

Scopes: `core`, `dashboard`, `scrapers`.

## Reporting bugs and security issues

Open a GitHub issue for bugs and feature requests. For security problems, follow
[SECURITY.md](SECURITY.md) instead of filing a public issue.

## License

By contributing you agree that your contributions are licensed under the [MIT License](LICENSE).
