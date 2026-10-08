"""Canonical taxonomy resolver for skills, keywords, and categorical values.

The ``TaxonomyResolver`` maps every observed variant of a skill, behavioral
keyword, career goal, boosted keyword, or job category to a single canonical
slug.  This eliminates deduplication problems across scrapers, profiles, and
the scoring engine.

Usage::

    from job_engine.taxonomy import TaxonomyResolver

    resolver = TaxonomyResolver(session)
    slug = resolver.resolve("ML", "skill")          # → "machine_learning"
    slugs = resolver.resolve_many(["ML", "Python"], "skill")  # → ["machine_learning", "python"]
    label = resolver.get_label("machine_learning")  # → "Machine Learning"

    # Auto-registers unknown variants with first-seen spelling as canonical
    slug = resolver.resolve("some_new_skill")       # → "some_new_skill"
"""

import logging
import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from job_engine.models import TaxonomySynonym, TaxonomyTerm

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Built-in seed map — canonical skill/value aliases distilled from SKILLS_REGEX
# and _DEFAULT_SKILL_CLUSTERS.  Each entry maps: canonical_slug -> [variants...]
# This is the source of truth for the bootstrap.
# ---------------------------------------------------------------------------

# Label overrides for slugs where _build_label(slug) produces incorrect results
# (acronyms, brand names, CamelCase terms not handled by .title()).
# Key: lowercase slug, Value: proper display label.
_LABEL_OVERRIDES: dict[str, str] = {
    "typescript": "TypeScript",
    "javascript": "JavaScript",
    "pytorch": "PyTorch",
    "fastapi": "FastAPI",
    "next_js": "Next.js",
    "node_js": "Node.js",
    "react": "React",
    "vue": "Vue",
    "nuxt": "Nuxt",
    "svelte": "Svelte",
    "github_actions": "GitHub Actions",
    "cplusplus": "C++",
    "ai": "AI",
    "aws": "AWS",
    "gcp": "GCP",
    "azure": "Azure",
    "sql": "SQL",
    "api": "API",
    "rest_api": "REST API",
    "ci_cd": "CI/CD",
    "ios": "iOS",
    "macos": "macOS",
    "dotnet": ".NET",
    "dotnet_core": ".NET Core",
    "aspnet": "ASP.NET",
}

SEED_ALIASES: dict[str, dict[str, list[str]]] = {
    "skill": {
        # Core languages & frameworks
        "python": [],
        "fastapi": [],
        "pydantic": [],
        "asyncio": [],
        "celery": [],
        "websockets": ["web_sockets"],
        "pytest": [],
        "postgresql": ["postgres", "psql"],
        "sqlalchemy": [],
        "alembic": [],
        "sql": [],
        "asyncpg": [],
        "mongodb": ["mongo"],
        "redis": [],
        "cassandra": [],
        "elasticsearch": ["es"],
        "pandas": [],
        "numpy": [],
        "scikit_learn": ["sklearn", "scikit learn"],
        "tensorflow": ["tf"],
        "pytorch": ["torch"],
        "langchain": [],
        "llm": ["large language model", "large_language_model"],
        "plotly": [],
        "dash": [],
        "matplotlib": [],
        "streamlit": [],
        "docker": ["containerization"],
        "aws": ["amazon_web_services"],
        "lambda": [],
        "github_actions": ["ci_cd", "gitlab_ci"],
        "trading": [],
        "fintech": ["financial_technology"],
        "machine_learning": ["ml", "machine learning"],
        "ai": ["artificial_intelligence"],
        "react": ["reactjs", "react_js"],
        "typescript": ["ts"],
        "javascript": ["js", "node_js"],
        "node": ["nodejs", "node_js"],
        "go": ["golang"],
        "rust": [],
        "graphql": [],
        "kubernetes": ["k8s"],
        "django": [],
        "flask": [],
        "terraform": [],
        "google_cloud": ["gcp", "google cloud"],
        "azure": [],
        "api": [],
        "bot": [],
        "telegram": [],
        "discord": [],
        "web_scraping": ["web scraping", "scraping"],
        "backtesting": [],
        "quantitative": ["quant"],
        "solidity": [],
        "web3": ["web_3"],
        "ethereum": ["eth"],
        "bitcoin": ["btc"],
        "defi": [],
        "blockchain": [],
        "smart_contracts": ["smart contract"],
        "data_science": ["data science"],
        "devops": [],
        "full_stack": ["fullstack", "full stack"],
        "backend": [],
        "nosql": ["no_sql"],
        "cplusplus": ["c++", "cpp", "cxx"],
        "dotnet": [".net", "dot_net"],
    },
    "behavioral": {
        "collaboration": ["teamwork", "collaborative"],
        "ownership": ["accountability", "take ownership"],
        "mentorship": ["mentoring"],
        "agile": ["scrum", "kanban"],
        "continuous_improvement": ["continuous improvement", "kaizen", "retrospective"],
        "communication": ["written communication", "verbal communication"],
        "leadership": [],
        "problem_solving": ["analytical", "critical thinking"],
        "adaptability": ["flexible", "learning agility"],
    },
    "career": {
        "tech_lead": ["tech lead", "technical lead"],
        "architecture": ["system design", "software architecture"],
        "distributed_systems": ["distributed systems", "microservices"],
        "machine_learning": ["ml", "machine learning", "ai"],
        "mentoring": ["coaching"],
        "cto": ["chief technology officer"],
        "data_science": ["data science", "data scientist"],
        "full_stack": ["fullstack", "full stack"],
    },
    "boosted": {
        "trading": ["algorithmic trading"],
        "fintech": ["financial technology"],
        "machine_learning": ["ml", "machine learning"],
        "python": [],
        "fastapi": [],
        "backtesting": [],
    },
    "category": {
        "backend": ["back-end", "back_end"],
        "frontend": ["front-end", "front_end", "frontend"],
        "fullstack": ["full-stack", "full_stack", "full stack"],
        "data": ["data science", "data engineering", "data_science"],
        "devops": ["devops", "sre", "platform engineering"],
        "mobile": ["ios", "android", "mobile development"],
        "ai": ["artificial intelligence", "machine learning", "ml"],
        "blockchain": ["web3", "crypto"],
        "security": ["cybersecurity", "infosec"],
    },
}


def _canonicalize_variant(variant: str) -> str:
    """Normalize a variant string to a canonical slug form.

    Lowercases, strips, replaces spaces/special chars with underscores,
    collapses multiple underscores, and strips leading/trailing underscores.
    """
    s = variant.lower().strip()
    s = re.sub(r"[^a-z0-9_\s]", " ", s)
    s = re.sub(r"\s+", "_", s)
    s = re.sub(r"_+", "_", s)
    s = s.strip("_")
    return s if s else variant.lower().strip()


def _build_label(slug: str) -> str:
    """Convert a slug to a display label: 'machine_learning' -> 'Machine Learning'."""
    if slug in _LABEL_OVERRIDES:
        return _LABEL_OVERRIDES[slug]
    return slug.replace("_", " ").title()


class TaxonomyResolver:
    """Resolves skill/keyword variants to canonical slugs using the DB taxonomy registry.

    Provides fast in-memory caching.  Auto-registers unknown variants with
    their first-seen form as the canonical slug.
    """

    def __init__(self, session: Session | None = None):
        self._session = session
        # variant -> slug cache
        self._variant_cache: dict[str, str] = {}
        # slug -> {label, category}
        self._term_cache: dict[str, dict[str, str]] = {}
        # slug -> [variants...] for text search
        self._variant_list_cache: dict[str, list[str]] = {}
        self._loaded = False
        self._seed_builtins()

    def _seed_builtins(self) -> None:
        """Seed in-memory cache from SEED_ALIASES (built-in map)."""
        for category, aliases in SEED_ALIASES.items():
            for canonical, variants in aliases.items():
                slug = _canonicalize_variant(canonical)
                if slug in self._term_cache:
                    continue
                self._term_cache[slug] = {
                    "label": _build_label(slug),
                    "category": category,
                }
                self._cache_variant(slug, slug)
                for v in variants:
                    self._cache_variant(slug, v)
                    self._cache_variant(slug, _canonicalize_variant(v))

    def _ensure_loaded(self) -> None:
        """Load all taxonomy terms and synonyms from DB into cache (overlays built-ins)."""
        if self._loaded or self._session is None:
            return
        try:
            terms = self._session.execute(select(TaxonomyTerm)).scalars().all()
            for term in terms:
                slug = term.slug
                self._term_cache[slug] = {
                    "label": term.label or _build_label(slug),
                    "category": term.category,
                }
                variants = [slug]
                for syn in term.synonyms:
                    self._variant_cache[syn.variant] = slug
                    variants.append(syn.variant)
                self._variant_list_cache[slug] = variants
            self._loaded = True
        # Graceful degradation — system can operate without DB taxonomy
        except Exception:
            logger.warning("Failed to load taxonomy from DB — using built-in cache", exc_info=True)

    def _cache_variant(self, slug: str, variant: str) -> None:
        """Point *variant* at its canonical *slug* and record it in the variant list.

        The canonical slug is always the first entry of its own variant list;
        variants are appended only once (deduplicated).
        """
        self._variant_cache[variant] = slug
        variants = self._variant_list_cache.setdefault(slug, [slug])
        if variant not in variants:
            variants.append(variant)

    def _get_or_create_term(
        self, slug: str, category: str, label: str
    ) -> "tuple[TaxonomyTerm, bool]":
        """Fetch the term for *slug*, creating it if absent.

        Returns ``(term, created)`` where *created* is True if a new row was
        inserted.  Assumes ``self._session`` is not None.
        """
        assert self._session is not None
        term = self._session.execute(
            select(TaxonomyTerm).where(TaxonomyTerm.slug == slug)
        ).scalar_one_or_none()
        if term is not None:
            return term, False
        term = TaxonomyTerm(slug=slug, category=category, label=label)
        self._session.add(term)
        self._session.flush()
        return term, True

    def resolve(self, variant: str, category: str = "skill") -> str:
        """Return canonical slug for any variant. Auto-registers unknown variants."""
        self._ensure_loaded()
        variant = variant.strip()
        if not variant:
            return ""

        # Check cache first
        if variant in self._variant_cache:
            return self._variant_cache[variant]

        # Try normalized form
        normalized = _canonicalize_variant(variant)
        if normalized in self._variant_cache:
            slug = self._variant_cache[normalized]
            self._variant_cache[variant] = slug
            return slug

        # Try direct slug match
        if normalized in self._term_cache:
            self._variant_cache[variant] = normalized
            self._variant_cache[normalized] = normalized
            return normalized

        # Auto-register: first-seen spelling becomes canonical slug
        slug = normalized
        label = _build_label(slug)

        if self._session is not None:
            try:
                # first-seen spelling becomes canonical, unless the term already
                # exists (created concurrently or previously) — then adopt it.
                term, created = self._get_or_create_term(slug, category, label)
                syn = TaxonomySynonym(term_id=term.id, variant=variant, source="auto", seen_count=1)
                self._session.add(syn)
                self._session.flush()
                if not created:
                    slug = term.slug
                    label = term.label or _build_label(slug)
            except (OSError, ValueError, IntegrityError):
                logger.warning("Failed to persist taxonomy term %r — continuing in-memory", slug)
                self._session.rollback()

        # Update caches
        self._term_cache[slug] = {"label": label, "category": category}
        self._cache_variant(slug, slug)
        self._cache_variant(slug, variant)

        return slug

    def resolve_many(self, variants: list[str], category: str = "skill") -> list[str]:
        """Batch resolve + deduplicate. Returns sorted list of unique slugs."""
        slugs: set[str] = set()
        for v in variants:
            slug = self.resolve(v, category)
            if slug:
                slugs.add(slug)
        return sorted(slugs)

    def get_label(self, slug: str) -> str:
        """Return display label for a slug."""
        self._ensure_loaded()
        if slug in self._term_cache:
            return self._term_cache[slug]["label"]
        return _build_label(slug)

    def get_variants(self, slug: str) -> list[str]:
        """Return all registered variants of a slug (for text searching)."""
        self._ensure_loaded()
        return self._variant_list_cache.get(slug, [slug])

    def canonicalize_for_text_search(self, slug: str) -> list[str]:
        """Return [canonical_label, *all_variants] for substring matching.

        Use this to search job text for both the canonical form and any
        known aliases (e.g. searching for 'machine_learning' and 'ml').
        Results are deduplicated and lowercase.
        """
        result = {slug}
        for v in self.get_variants(slug):
            # Normalize variant to the same form used in text search
            clean = _canonicalize_variant(v)
            if clean:
                result.add(clean)
            # Also add the raw variant (some match better in raw text)
            result.add(v.lower().strip())
        return sorted(result)

    def register(
        self, variant: str, canonical: str, category: str = "skill", source: str = "user"
    ) -> str:
        """Explicitly register a variant -> canonical mapping.

        If the canonical slug doesn't exist yet, it's created.  The variant
        is then associated with it.
        """
        self._ensure_loaded()
        canonical_slug = _canonicalize_variant(canonical)

        if self._session is not None:
            try:
                term, _ = self._get_or_create_term(
                    canonical_slug, category, _build_label(canonical_slug)
                )
                # Register variant as a synonym (bump seen_count if it already exists)
                existing_syn = self._session.execute(
                    select(TaxonomySynonym).where(TaxonomySynonym.variant == variant)
                ).scalar_one_or_none()
                if existing_syn is None:
                    syn = TaxonomySynonym(
                        term_id=term.id, variant=variant, source=source, seen_count=1
                    )
                    self._session.add(syn)
                    self._session.flush()
                else:
                    existing_syn.term_id = term.id
                    existing_syn.seen_count = TaxonomySynonym.seen_count + 1
            except (OSError, ValueError, IntegrityError):
                logger.warning(
                    "Failed to register taxonomy mapping %r -> %r", variant, canonical_slug
                )
                self._session.rollback()

        # Update caches
        self._term_cache[canonical_slug] = {
            "label": _build_label(canonical_slug),
            "category": category,
        }
        self._cache_variant(canonical_slug, canonical_slug)
        self._cache_variant(canonical_slug, variant)

        return canonical_slug

    def get_all_terms(self, category: str | None = None) -> list[dict[str, Any]]:
        """Return all registered terms, optionally filtered by category."""
        self._ensure_loaded()
        results = []
        for slug, info in self._term_cache.items():
            if category is None or info["category"] == category:
                results.append(
                    {
                        "slug": slug,
                        "label": info["label"],
                        "category": info["category"],
                        "variants": self._variant_list_cache.get(slug, [slug]),
                    }
                )
        return results


# ---------------------------------------------------------------------------
# Module-level helper: build a resolver from a sync engine
# ---------------------------------------------------------------------------


def get_resolver(engine=None) -> TaxonomyResolver:
    """Create a TaxonomyResolver using a sync DB session.

    If no engine is provided, uses the default sync engine.
    """
    from job_engine.database import get_sync_engine

    if engine is None:
        engine = get_sync_engine()
    session = Session(engine)
    return TaxonomyResolver(session)


def seed_taxonomy_from_builtins(session: Session) -> int:
    """Seed the taxonomy registry from built-in SEED_ALIASES.

    Returns the number of terms created.
    """
    count = 0
    # Track which variant-slug mappings we've already registered
    registered_variants: set[str] = set()

    for category, aliases in SEED_ALIASES.items():
        for canonical, variants in aliases.items():
            slug = _canonicalize_variant(canonical)
            existing = session.execute(
                select(TaxonomyTerm).where(TaxonomyTerm.slug == slug)
            ).scalar_one_or_none()
            if existing is not None:
                continue  # already seeded

            term = TaxonomyTerm(
                slug=slug,
                category=category,
                label=_build_label(slug),
            )
            session.add(term)
            session.flush()
            count += 1

            # Register the canonical slug as its own synonym (if not already registered)
            if canonical not in registered_variants:
                syn = TaxonomySynonym(
                    term_id=term.id, variant=canonical, source="builtin", seen_count=1
                )
                session.add(syn)
                registered_variants.add(canonical)

            # Register each alias variant (skip if already registered to another term)
            for v in variants:
                if v in registered_variants:
                    continue
                existing_syn = session.execute(
                    select(TaxonomySynonym).where(TaxonomySynonym.variant == v)
                ).scalar_one_or_none()
                if existing_syn is None:
                    syn = TaxonomySynonym(
                        term_id=term.id, variant=v, source="builtin", seen_count=1
                    )
                    session.add(syn)
                    registered_variants.add(v)

    session.commit()
    return count
