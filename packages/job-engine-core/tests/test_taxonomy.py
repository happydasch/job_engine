"""Tests for the canonical taxonomy resolver.

Covers both the in-memory (no session) path and the DB-backed path, which
previously had no coverage.
"""

import pytest
from job_engine.models import Base, TaxonomySynonym, TaxonomyTerm
from job_engine.taxonomy import (
    TaxonomyResolver,
    _build_label,
    _canonicalize_variant,
    seed_taxonomy_from_builtins,
)
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

# ── Fixtures ──────────────────────────────────────────────────────────────


@pytest.fixture
def db_session():
    """Bare in-memory DB (schema only, not seeded) with a live session."""
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = Session(engine)
    yield session
    session.close()
    Base.metadata.drop_all(engine)


# ── Pure helpers ────────────────────────────────────────────────────────────


class TestCanonicalizeVariant:
    def test_lowercases_and_underscores(self):
        assert _canonicalize_variant("Machine Learning") == "machine_learning"

    def test_strips_special_chars(self):
        assert _canonicalize_variant("C++") == "c"
        assert _canonicalize_variant("  React.js  ") == "react_js"

    def test_collapses_repeated_underscores(self):
        assert _canonicalize_variant("a - b") == "a_b"

    def test_empty_falls_back_to_lowercased_input(self):
        assert _canonicalize_variant("!!!") == "!!!"


class TestBuildLabel:
    def test_titlecases_plain_slug(self):
        assert _build_label("machine_learning") == "Machine Learning"

    def test_uses_override_for_acronyms(self):
        assert _build_label("typescript") == "TypeScript"
        assert _build_label("cplusplus") == "C++"
        assert _build_label("ci_cd") == "CI/CD"


# ── In-memory resolver (no session) ───────────────────────────────────────


class TestResolverInMemory:
    def test_resolves_seeded_variant_to_canonical(self):
        r = TaxonomyResolver()
        assert r.resolve("ML", "skill") == "machine_learning"
        assert r.resolve("k8s", "skill") == "kubernetes"

    def test_get_label_prefers_override(self):
        r = TaxonomyResolver()
        assert r.get_label("machine_learning") == "Machine Learning"
        assert r.get_label("typescript") == "TypeScript"

    def test_variant_list_has_canonical_slug_first(self):
        r = TaxonomyResolver()
        variants = r.get_variants("machine_learning")
        assert variants[0] == "machine_learning"
        assert "ml" in variants

    def test_auto_registers_unknown_variant(self):
        r = TaxonomyResolver()
        slug = r.resolve("Some Brand New Skill", "skill")
        assert slug == "some_brand_new_skill"
        # Resolving again is stable and cached.
        assert r.resolve("Some Brand New Skill", "skill") == slug

    def test_auto_registered_variant_list_starts_with_slug(self):
        r = TaxonomyResolver()
        slug = r.resolve("Foo Bar", "skill")
        variants = r.get_variants(slug)
        assert variants[0] == slug  # canonical slug always first
        assert "Foo Bar" in variants

    def test_empty_variant_returns_empty(self):
        r = TaxonomyResolver()
        assert r.resolve("   ", "skill") == ""

    def test_resolve_many_dedupes_and_sorts(self):
        r = TaxonomyResolver()
        assert r.resolve_many(["ML", "machine learning", "Python"]) == [
            "machine_learning",
            "python",
        ]

    def test_text_search_includes_slug_and_variants(self):
        r = TaxonomyResolver()
        terms = r.canonicalize_for_text_search("machine_learning")
        assert "machine_learning" in terms
        assert "ml" in terms
        assert "machine learning" in terms


# ── DB-backed resolver ────────────────────────────────────────────────────


class TestResolverWithSession:
    def test_auto_register_persists_term_and_synonym(self, db_session):
        r = TaxonomyResolver(db_session)
        slug = r.resolve("Kubernetes Operators", "skill")
        assert slug == "kubernetes_operators"

        term = db_session.execute(
            select(TaxonomyTerm).where(TaxonomyTerm.slug == slug)
        ).scalar_one_or_none()
        assert term is not None
        assert term.category == "skill"
        assert term.label == "Kubernetes Operators"

        syn = db_session.execute(
            select(TaxonomySynonym).where(TaxonomySynonym.variant == "Kubernetes Operators")
        ).scalar_one_or_none()
        assert syn is not None
        assert syn.source == "auto"
        assert syn.term_id == term.id

    def test_auto_register_adopts_term_created_after_load(self, db_session):
        r = TaxonomyResolver(db_session)
        r.resolve("python")  # force _ensure_loaded so the cache is populated

        # Simulate a concurrent writer inserting the term after we loaded.
        db_session.add(
            TaxonomyTerm(slug="kubernetes_operators", category="skill", label="Custom KO")
        )
        db_session.flush()

        # Auto-register hits _get_or_create_term → term already exists → adopt it.
        slug = r.resolve("Kubernetes Operators", "skill")
        assert slug == "kubernetes_operators"
        assert r.get_label("kubernetes_operators") == "Custom KO"

    def test_register_creates_mapping(self, db_session):
        r = TaxonomyResolver(db_session)
        canonical = r.register("K8s Op", "kubernetes operators", "skill", "user")
        assert canonical == "kubernetes_operators"
        assert r.resolve("K8s Op", "skill") == canonical

        syn = db_session.execute(
            select(TaxonomySynonym).where(TaxonomySynonym.variant == "K8s Op")
        ).scalar_one_or_none()
        assert syn is not None
        assert syn.source == "user"

    def test_get_all_terms_filters_by_category(self, db_session):
        r = TaxonomyResolver(db_session)
        skills = r.get_all_terms(category="skill")
        assert all(t["category"] == "skill" for t in skills)
        assert any(t["slug"] == "python" for t in skills)


# ── Seeding ─────────────────────────────────────────────────────────────────


class TestSeedTaxonomy:
    def test_seed_creates_terms_and_is_idempotent(self, db_session):
        first = seed_taxonomy_from_builtins(db_session)
        assert first > 0
        second = seed_taxonomy_from_builtins(db_session)
        assert second == 0

    def test_seeded_terms_are_resolvable(self, db_session):
        seed_taxonomy_from_builtins(db_session)
        r = TaxonomyResolver(db_session)
        assert r.resolve("ML", "skill") == "machine_learning"
