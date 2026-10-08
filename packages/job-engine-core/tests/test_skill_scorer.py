"""
Tests for the profile-to-job matching engine.

Tests scoring dimensions independently and the integrated score.
"""

from job_engine.skill_scorer import (
    CRITICAL_BONUS_PER_MATCH,
    WEIGHTS,
    JobMatcher,
    score_all_jobs,
)


class TestJobMatcher:
    """Integration tests for JobMatcher."""

    def test_matcher_initializes_with_profile(self, mock_profile_path):
        """Matcher should load profile and build indices."""
        matcher = JobMatcher(mock_profile_path)
        assert "python" in matcher.all_skills
        assert "fastapi" in matcher.boosted_keywords

    def test_score_returns_float(self, mock_profile_path, sample_jobs):
        """score() should return a float 0-100."""
        matcher = JobMatcher(mock_profile_path)
        for job in sample_jobs:
            score = matcher.score(job)
            assert isinstance(score, float)
            assert 0 <= score <= 100

    def test_score_detail_has_components(self, mock_profile_path, sample_jobs):
        """score_detail() should return breakdown with components."""
        matcher = JobMatcher(mock_profile_path)
        for job in sample_jobs:
            details = matcher.score_detail(job)
            assert "total_score" in details
            assert "components" in details
            assert "reason" in details

    def test_python_job_scores_high(self, mock_profile_path, sample_jobs):
        """Python/FastAPI senior remote job should score well."""
        matcher = JobMatcher(mock_profile_path)
        python_job = sample_jobs[0]  # Python Backend Developer
        score = matcher.score(python_job)
        assert score >= 40, f"Expected ≥40, got {score}"

    def test_irrelevant_job_scores_low(self, mock_profile_path, sample_jobs):
        """Junior Java office job should score lower than Python Backend job."""
        matcher = JobMatcher(mock_profile_path)
        python_job = sample_jobs[0]  # Python Backend Developer
        java_job = sample_jobs[2]  # Junior Java Developer
        python_score = matcher.score(python_job)
        java_score = matcher.score(java_job)
        assert java_score < python_score, (
            f"Expected Java job ({java_score}) < Python job ({python_score})"
        )

    def test_score_all_jobs(self, mock_profile_path, sample_jobs):
        """score_all_jobs should return sorted enriched jobs."""
        results = score_all_jobs(sample_jobs, profile_path=mock_profile_path)
        assert len(results) == len(sample_jobs)
        assert all("match_score" in j for j in results)
        # Should be sorted descending
        scores = [j["match_score"] for j in results]
        assert scores == sorted(scores, reverse=True)


# ── Edge cases ─────────────────────────────────────────────────────


class TestEdgeCases:
    """Tests for edge cases and robustness."""

    def test_empty_job_skills(self, mock_profile_path):
        """Job with empty skills should not crash."""
        matcher = JobMatcher(mock_profile_path)
        job = {"title": "Test", "skills": []}
        score = matcher.score(job)
        assert isinstance(score, float)
        assert 0 <= score <= 100

    def test_no_salary_job(self, mock_profile_path):
        """Job with no salary info should not crash scoring."""
        matcher = JobMatcher(mock_profile_path)
        job = {
            "external_id": "test_004",
            "platform": "justjoin.it",
            "title": "No Salary Role",
            "company": "TestCorp",
            "location": "Remote",
            "remote": True,
            "skills": ["python"],
        }
        score = matcher.score(job)
        assert isinstance(score, float)

    def test_null_description_job(self, mock_profile_path):
        """Job with null description should not crash keyword scoring."""
        matcher = JobMatcher(mock_profile_path)
        job = {
            "external_id": "test_005",
            "platform": "upwork.com",
            "title": "Some Job",
            "company": "Test",
            "description": None,
            "skills": ["python"],
        }
        score = matcher.score(job)
        assert isinstance(score, float)

    def test_non_ascii_characters(self, mock_profile_path):
        """Non-ASCII characters should not break scoring."""
        matcher = JobMatcher(mock_profile_path)
        job = {
            "external_id": "test_006",
            "platform": "justjoin.it",
            "title": "Python开发工程师",
            "company": "科技公司",
            "description": "需要会python和fastapi",
            "skills": ["python", "fastapi"],
            "location": "Remote",
            "remote": True,
        }
        score = matcher.score(job)
        assert isinstance(score, float)

    def test_partial_skill_match(self, mock_profile_path):
        """Skills with underscore/space/hyphen differences should still match."""
        matcher = JobMatcher(mock_profile_path)
        # Our profile has "github_actions". Job lists "github actions".
        job = {
            "external_id": "test_007",
            "platform": "justjoin.it",
            "title": "DevOps Role",
            "company": "ShipIt Inc",
            "skills": ["python", "github actions", "docker"],
            "location": "Remote",
            "remote": True,
        }
        details = matcher.score_detail(job)
        skill_score = details["components"]["skill_overlap"]["score"]
        assert skill_score > 0, "Should match 'github actions' with profile 'github_actions'"

    def test_score_detail_reports_skill_gap(self, mock_profile_path):
        """skill_gap splits the job's skills into matched vs missing for the profile."""
        matcher = JobMatcher(mock_profile_path)
        job = {
            "external_id": "test_gap",
            "platform": "test",
            "title": "Backend",
            "company": "Gap Inc",
            "skills_slugs": ["python", "cobol"],
        }
        gap = matcher.score_detail(job)["skill_gap"]
        assert gap == {"matched": ["python"], "missing": ["cobol"]}

    def test_all_weights_sum_to_one(self):
        """All scoring weights should sum to 1.0 (8 dimensions)."""
        total = sum(WEIGHTS.values())
        assert abs(total - 1.0) < 0.01, f"Weights sum to {total}, expected 1.0"
        assert len(WEIGHTS) == 8, f"Expected 8 dimensions, got {len(WEIGHTS)}"


class TestScoringDimensions:
    """Test each scoring dimension in isolation."""

    def test_skill_overlap(self, mock_profile_path, sample_jobs):
        matcher = JobMatcher(mock_profile_path)
        job = sample_jobs[0]  # python, fastapi, postgresql, docker, redis
        details = matcher.score_detail(job)
        skill_score = details["components"]["skill_overlap"]["score"]
        assert skill_score > 0, "Should have skill overlap"

    def test_keyword_boost(self, mock_profile_path, sample_jobs):
        matcher = JobMatcher(mock_profile_path)
        # Fintech job with trading keywords
        job = sample_jobs[1]  # Fintech Inc, has trading
        details = matcher.score_detail(job)
        kw_score = details["components"]["keyword_boost"]["score"]
        assert kw_score > 0, "Should have keyword boost"

    def test_excluded_company_scores_zero(self, mock_profile_path, sample_jobs):
        matcher = JobMatcher(mock_profile_path)
        matcher.excluded_companies = ["oldcorp"]
        score = matcher.score(sample_jobs[2])
        assert score == 0.0, "Excluded company should score 0"


class TestNewDimensions:
    """Tests for the 4 new scoring dimensions."""

    def test_location_fit_remote_only(self, mock_profile_path):
        """Remote job with remote_only=True in profile should score 100 in location."""
        matcher = JobMatcher(mock_profile_path)
        job = {
            "external_id": "loc_001",
            "title": "Remote Role",
            "company": "Test",
            "remote": True,
            "location": "Remote",
            "skills": ["python"],
        }
        details = matcher.score_detail(job)
        loc_score = details["components"]["location_fit"]["score"]
        assert loc_score == 100.0, f"Expected 100 for remote job, got {loc_score}"

    def test_location_fit_preferred_city(self, mock_profile_path):
        """Job in a preferred city (warsaw) should score 100."""
        matcher = JobMatcher(mock_profile_path)
        job = {
            "external_id": "loc_002",
            "title": "Office Role",
            "company": "Warsaw Inc",
            "remote": False,
            "location": "Warsaw",
            "city": "Warsaw",
            "skills": ["python"],
        }
        details = matcher.score_detail(job)
        loc_score = details["components"]["location_fit"]["score"]
        assert loc_score == 100.0, f"Expected 100 for Warsaw, got {loc_score}"

    def test_location_fit_non_remote_non_preferred(self, mock_profile_path):
        """Non-remote job outside preferred locations with remote_only=True → 0."""
        matcher = JobMatcher(mock_profile_path)
        job = {
            "external_id": "loc_003",
            "title": "Office Role",
            "company": "Berlin GmbH",
            "remote": False,
            "location": "Berlin",
            "skills": ["python"],
        }
        details = matcher.score_detail(job)
        loc_score = details["components"]["location_fit"]["score"]
        assert loc_score == 0.0, f"Expected 0 for Berlin (remote_only), got {loc_score}"

    def test_rate_fit_within_range(self, mock_profile_path):
        """Salary within profile's expected USD range should score high (>80)."""
        matcher = JobMatcher(mock_profile_path)
        job = {
            "external_id": "rate_001",
            "title": "Good Rate Role",
            "company": "Test",
            "salary_min": 6000,
            "salary_max": 9000,
            "currency": "USD",
            "skills": ["python"],
        }
        details = matcher.score_detail(job)
        rate_score = details["components"]["rate_fit"]["score"]
        assert rate_score >= 80.0, f"Expected >=80 for good rate, got {rate_score}"

    def test_rate_fit_below_minimum(self, mock_profile_path):
        """Salary below profile minimum should score low."""
        matcher = JobMatcher(mock_profile_path)
        job = {
            "external_id": "rate_002",
            "title": "Low Rate Role",
            "company": "Test",
            "salary_min": 1000,
            "salary_max": 2000,
            "currency": "USD",
            "skills": ["python"],
        }
        details = matcher.score_detail(job)
        rate_score = details["components"]["rate_fit"]["score"]
        assert rate_score < 50.0, f"Expected <50 for low rate, got {rate_score}"

    def test_rate_fit_above_maximum(self, mock_profile_path):
        """Salary above profile max should score 80 (opportunity)."""
        matcher = JobMatcher(mock_profile_path)
        job = {
            "external_id": "rate_003",
            "title": "High Rate Role",
            "company": "Test",
            "salary_min": 12000,
            "salary_max": 15000,
            "currency": "USD",
            "skills": ["python"],
        }
        details = matcher.score_detail(job)
        rate_score = details["components"]["rate_fit"]["score"]
        assert rate_score == 80.0, f"Expected 80 for above-max rate, got {rate_score}"

    def test_rate_fit_no_salary_neutral(self, mock_profile_path):
        """Job with no salary data → neutral score of 50."""
        matcher = JobMatcher(mock_profile_path)
        job = {
            "external_id": "rate_004",
            "title": "No Salary Role",
            "company": "Test",
            "skills": ["python"],
        }
        details = matcher.score_detail(job)
        rate_score = details["components"]["rate_fit"]["score"]
        assert rate_score == 50.0, f"Expected 50 for no salary, got {rate_score}"

    def test_rate_fit_different_currency(self, mock_profile_path):
        """EUR salary compared raw (no exchange_rates in profile) should still work."""
        matcher = JobMatcher(mock_profile_path)
        # 6000-8000 EUR, no exchange_rates set in mock profile
        # Raw comparison: 6000-8000 intersects profile 5000-10000
        job = {
            "external_id": "rate_005",
            "title": "EUR Role",
            "company": "Test",
            "salary_min": 6000,
            "salary_max": 8000,
            "currency": "EUR",
            "skills": ["python"],
        }
        details = matcher.score_detail(job)
        rate_score = details["components"]["rate_fit"]["score"]
        assert rate_score > 50.0, f"Expected >50 for EUR within range, got {rate_score}"

    def test_category_fit_matched(self, mock_profile_path):
        """Backend category job (matches profile skill category) should get 100."""
        matcher = JobMatcher(mock_profile_path)
        job = {
            "external_id": "cat_001",
            "title": "Backend Dev",
            "company": "Test",
            "category": "backend",
            "skills": ["python"],
        }
        details = matcher.score_detail(job)
        cat_score = details["components"]["category_fit"]["score"]
        assert cat_score == 100.0, f"Expected 100 for backend category, got {cat_score}"

    def test_category_fit_unmatched(self, mock_profile_path):
        """Unmatched category (no mapping, not in profile) should score neutral (50)."""
        matcher = JobMatcher(mock_profile_path)
        job = {
            "external_id": "cat_002",
            "title": "Mobile Dev",
            "company": "Test",
            "category": "mobile",
            "skills": ["kotlin"],
        }
        details = matcher.score_detail(job)
        cat_score = details["components"]["category_fit"]["score"]
        assert cat_score == 50.0, f"Expected 50 (neutral) for mobile category, got {cat_score}"

    def test_category_fit_no_category(self, mock_profile_path):
        """No category → neutral 50."""
        matcher = JobMatcher(mock_profile_path)
        job = {
            "external_id": "cat_003",
            "title": "No Category",
            "company": "Test",
            "skills": ["python"],
        }
        details = matcher.score_detail(job)
        cat_score = details["components"]["category_fit"]["score"]
        assert cat_score == 50.0, f"Expected 50 for no category, got {cat_score}"

    def test_experience_fit_exact(self, mock_profile_path):
        """Senior role with 5 years experience → exact match → 100."""
        matcher = JobMatcher(mock_profile_path)
        job = {
            "external_id": "exp_001",
            "title": "Senior Dev",
            "company": "Test",
            "experience_level": "senior",
            "skills": ["python"],
        }
        details = matcher.score_detail(job)
        exp_score = details["components"]["experience_fit"]["score"]
        assert exp_score == 100.0, f"Expected 100 for senior match, got {exp_score}"

    def test_experience_fit_one_step_below(self, mock_profile_path):
        """Mid level with 5 years → one step below senior → 70."""
        matcher = JobMatcher(mock_profile_path)
        job = {
            "external_id": "exp_002",
            "title": "Mid Dev",
            "company": "Test",
            "experience_level": "mid",
            "skills": ["python"],
        }
        details = matcher.score_detail(job)
        exp_score = details["components"]["experience_fit"]["score"]
        assert exp_score == 70.0, f"Expected 70 for mid (5yr profile), got {exp_score}"

    def test_experience_fit_junior_below(self, mock_profile_path):
        """Junior level with 5 years → two steps below → 30."""
        matcher = JobMatcher(mock_profile_path)
        job = {
            "external_id": "exp_003",
            "title": "Junior Dev",
            "company": "Test",
            "experience_level": "junior",
            "skills": ["python"],
        }
        details = matcher.score_detail(job)
        exp_score = details["components"]["experience_fit"]["score"]
        assert exp_score == 30.0, f"Expected 30 for junior (5yr profile), got {exp_score}"

    def test_experience_fit_no_level(self, mock_profile_path):
        """No experience level → neutral 50."""
        matcher = JobMatcher(mock_profile_path)
        job = {
            "external_id": "exp_004",
            "title": "No Level",
            "company": "Test",
            "skills": ["python"],
        }
        details = matcher.score_detail(job)
        exp_score = details["components"]["experience_fit"]["score"]
        assert exp_score == 50.0, f"Expected 50 for no level, got {exp_score}"

    def test_components_have_labels(self, mock_profile_path, sample_jobs):
        """Each component dict should include a human-readable label."""
        matcher = JobMatcher(mock_profile_path)
        details = matcher.score_detail(sample_jobs[0])
        for key, comp in details["components"].items():
            assert "label" in comp, f"Component {key} missing 'label'"
            assert isinstance(comp["label"], str), f"Label for {key} not a string"
            assert len(comp["label"]) > 0, f"Label for {key} is empty"

    def test_critical_bonus_cap(self, mock_profile_path):
        """Critical skill bonus should be capped at +20."""
        matcher = JobMatcher(mock_profile_path)
        # Profile critical categories: core_backend, databases_sql
        #   core_backend: python, fastapi, pydantic, asyncio, pytest
        #   databases_sql: postgresql, sqlalchemy, alembic, asyncpg
        #
        # 8 job skills, 5 matched, all 5 are critical:
        #   raw = 5/8 * 100 = 62.5
        #   bonus = min(5 × 5, 20) = 20  ← cap bites at 5 matches
        #   Without cap, bonus = 25 → 87.5
        #   With cap,    bonus = 20 → 82.5

        job = {
            "external_id": "crit_001",
            "title": "Critical Role",
            "company": "Test",
            "skills": [
                "python",
                "fastapi",
                "pydantic",  # 3 core_backend (critical)
                "postgresql",
                "sqlalchemy",  # 2 databases_sql (critical)
                "css",
                "html",
                "react",  # 3 non-matching
            ],
            "remote": True,
            "location": "Remote",
            "category": "python",
            "experience_level": "senior",
        }
        details = matcher.score_detail(job)
        skill_score = details["components"]["skill_overlap"]["score"]

        # Expected: 62.5 + 20 = 82.5
        assert skill_score == 82.5, f"Expected 82.5 (raw 62.5 + capped bonus 20), got {skill_score}"

        # Verify the cap is actually doing work: without it the score would be 87.5
        unlimited_bonus = 5 * CRITICAL_BONUS_PER_MATCH  # 25
        without_cap = (5 / 8) * 100 + unlimited_bonus  # 87.5
        assert skill_score < without_cap, (
            f"Cap not working: {skill_score} should be < {without_cap}"
        )

    def test_no_crash_on_missing_fields(self, mock_profile_path):
        """Jobs missing optional fields should not crash new dimensions."""
        matcher = JobMatcher(mock_profile_path)
        job = {
            "external_id": "minimal_001",
            "title": "Minimal",
            "company": "Test",
            "skills": ["python"],
        }
        details = matcher.score_detail(job)
        assert isinstance(details["total_score"], float)
        # All dimensions should still be present
        for dim in ("location_fit", "rate_fit", "category_fit", "experience_fit"):
            assert dim in details["components"], f"Missing component: {dim}"
            assert isinstance(details["components"][dim]["score"], float)


class TestNormalizeSkill:
    """Unit tests for normalize_skill()."""

    def test_dots_become_spaces(self):
        from job_engine.skill_scorer import normalize_skill

        assert normalize_skill("kat.b") == "kat b"

    def test_hyphens_become_spaces(self):
        from job_engine.skill_scorer import normalize_skill

        assert normalize_skill("machine-learning") == "machine learning"

    def test_numbers_preserved(self):
        from job_engine.skill_scorer import normalize_skill

        assert normalize_skill("python3") == "python3"

    def test_empty_string(self):
        from job_engine.skill_scorer import normalize_skill

        assert normalize_skill("") == ""

    def test_mixed_case_to_lowercase(self):
        from job_engine.skill_scorer import normalize_skill

        assert normalize_skill("FastAPI") == "fastapi"

    def test_underscores_become_spaces(self):
        from job_engine.skill_scorer import normalize_skill

        assert normalize_skill("github_actions") == "github actions"

    def test_whitespace_collapsed(self):
        from job_engine.skill_scorer import normalize_skill

        assert normalize_skill("  react   js  ") == "react js"

    def test_special_chars_replaced(self):
        from job_engine.skill_scorer import normalize_skill

        assert normalize_skill("C#") == "c"


class TestBehavioralFit:
    """Tests for the _score_behavioral dimension."""

    def test_behavioral_fit_matched(self, behavioral_profile_path):
        """Behavioral keywords in job text should yield high score (>50)."""
        matcher = JobMatcher(behavioral_profile_path)
        job = {
            "external_id": "beh_001",
            "title": "Collaborative Developer",
            "company": "Test",
            "description": "We value collaboration, ownership, and continuous improvement. "
            "Our agile team welcomes mentorship at all levels.",
            "skills": ["python"],
        }
        details = matcher.score_detail(job)
        beh_score = details["components"]["behavioral_fit"]["score"]
        assert beh_score > 50.0, f"Expected >50 for matched behavioral, got {beh_score}"

    def test_behavioral_fit_no_match(self, behavioral_profile_path):
        """No behavioral keywords in job text → 25 (mild penalty)."""
        matcher = JobMatcher(behavioral_profile_path)
        job = {
            "external_id": "beh_002",
            "title": "Solo Isolated Role",
            "company": "Test",
            "description": "Just code with no interaction with anyone else whatsoever.",
            "skills": ["python"],
        }
        details = matcher.score_detail(job)
        beh_score = details["components"]["behavioral_fit"]["score"]
        assert beh_score == 25.0, f"Expected 25 for no match, got {beh_score}"

    def test_behavioral_fit_no_keywords(self, mock_profile_path):
        """Profile without behavioral_keywords → neutral 50."""
        matcher = JobMatcher(mock_profile_path)
        job = {
            "external_id": "beh_003",
            "title": "Some Role",
            "company": "Test",
            "skills": ["python"],
        }
        details = matcher.score_detail(job)
        beh_score = details["components"]["behavioral_fit"]["score"]
        assert beh_score == 50.0, f"Expected 50 (neutral), got {beh_score}"

    def test_behavioral_fit_legacy_dict(self, legacy_behavioral_profile_path):
        """Legacy dict-of-lists format for behavioral_keywords should still work."""
        matcher = JobMatcher(legacy_behavioral_profile_path)
        job = {
            "external_id": "beh_004",
            "title": "Team Player",
            "company": "Test",
            "description": "We need collaboration and ownership. Teamwork matters here.",
            "skills": ["python"],
        }
        details = matcher.score_detail(job)
        beh_score = details["components"]["behavioral_fit"]["score"]
        assert beh_score > 50.0, f"Expected >50 for legacy dict match, got {beh_score}"


class TestCareerAlignment:
    """Tests for the _score_career dimension."""

    def test_career_alignment_matched(self, behavioral_profile_path):
        """Career keywords in job text should yield high score (>50)."""
        matcher = JobMatcher(behavioral_profile_path)
        job = {
            "external_id": "car_001",
            "title": "Tech Lead — Distributed Systems",
            "company": "Test",
            "description": "Leading architecture for distributed systems with ML components.",
            "skills": ["python"],
        }
        details = matcher.score_detail(job)
        car_score = details["components"]["career_alignment"]["score"]
        assert car_score > 50.0, f"Expected >50 for career match, got {car_score}"

    def test_career_alignment_no_match(self, behavioral_profile_path):
        """No career keywords in job text → 25 (mild penalty)."""
        matcher = JobMatcher(behavioral_profile_path)
        job = {
            "external_id": "car_002",
            "title": "Data Entry Clerk",
            "company": "Test",
            "description": "Entering data into spreadsheets all day.",
            "skills": ["excel"],
        }
        details = matcher.score_detail(job)
        car_score = details["components"]["career_alignment"]["score"]
        assert car_score == 25.0, f"Expected 25 for no match, got {car_score}"

    def test_career_alignment_no_keywords(self, mock_profile_path):
        """Profile without career_goals → neutral 50."""
        matcher = JobMatcher(mock_profile_path)
        job = {
            "external_id": "car_003",
            "title": "Some Role",
            "company": "Test",
            "skills": ["python"],
        }
        details = matcher.score_detail(job)
        car_score = details["components"]["career_alignment"]["score"]
        assert car_score == 50.0, f"Expected 50 (neutral), got {car_score}"

    def test_career_alignment_legacy_dict(self, legacy_behavioral_profile_path):
        """Legacy dict-of-lists format for career_goals should still work."""
        matcher = JobMatcher(legacy_behavioral_profile_path)
        job = {
            "external_id": "car_004",
            "title": "Architect",
            "company": "Test",
            "description": "Looking for a tech lead to drive architecture decisions.",
            "skills": ["python"],
        }
        details = matcher.score_detail(job)
        car_score = details["components"]["career_alignment"]["score"]
        assert car_score > 50.0, f"Expected >50 for legacy dict career match, got {car_score}"


class TestCategoryMappings:
    """Tests for category_mappings-driven _score_category."""

    def test_category_mapping_matched(self, category_mappings_profile_path):
        """Mapped category ('python' → ['backend']) should score 100."""
        matcher = JobMatcher(category_mappings_profile_path)
        job = {
            "external_id": "cm_001",
            "title": "Python Dev",
            "company": "Test",
            "category": "python",
            "skills": ["python"],
        }
        details = matcher.score_detail(job)
        cat_score = details["components"]["category_fit"]["score"]
        assert cat_score == 100.0, f"Expected 100 for mapped category, got {cat_score}"

    def test_category_mapping_unmapped(self, category_mappings_profile_path):
        """Unknown mapped category → neutral 50."""
        matcher = JobMatcher(category_mappings_profile_path)
        job = {
            "external_id": "cm_002",
            "title": "Mobile Dev",
            "company": "Test",
            "category": "mobile",
            "skills": ["kotlin"],
        }
        details = matcher.score_detail(job)
        cat_score = details["components"]["category_fit"]["score"]
        assert cat_score == 50.0, f"Expected 50 for unknown mapped category, got {cat_score}"

    def test_category_mapping_empty(self, category_mappings_profile_path):
        """Mapped category with empty list (frontend → []) should score 0."""
        matcher = JobMatcher(category_mappings_profile_path)
        job = {
            "external_id": "cm_003",
            "title": "Frontend Dev",
            "company": "Test",
            "category": "frontend",
            "skills": ["javascript"],
        }
        details = matcher.score_detail(job)
        cat_score = details["components"]["category_fit"]["score"]
        assert cat_score == 0.0, f"Expected 0 for empty mapping, got {cat_score}"


class TestExperienceFitCustom:
    """Tests for custom experience_levels and combined levels."""

    def test_experience_custom_levels(self, category_mappings_profile_path):
        """Profile-driven experience_levels dict (staff=4, senior=3) with profile 5yr → senior=3."""
        matcher = JobMatcher(category_mappings_profile_path)
        # Profile has custom levels: intern=0, junior=1, mid=2, senior=3, staff=4, principal=5
        # Profile years=5 → senior (level 3)
        # Staff level (4) is one step above → 100 (reach role)
        job = {
            "external_id": "exp_custom_001",
            "title": "Staff Engineer",
            "company": "Test",
            "experience_level": "staff",
            "skills": ["python"],
        }
        details = matcher.score_detail(job)
        exp_score = details["components"]["experience_fit"]["score"]
        assert exp_score == 100.0, f"Expected 100 (one step above senior), got {exp_score}"

    def test_experience_combined_level(self, mock_profile_path):
        """Job with 'mid/senior' level where profile is senior → should match 'senior'."""
        matcher = JobMatcher(mock_profile_path)
        job = {
            "external_id": "exp_comb_001",
            "title": "Mid/Senior Dev",
            "company": "Test",
            "experience_level": "mid/senior",
            "skills": ["python"],
        }
        details = matcher.score_detail(job)
        exp_score = details["components"]["experience_fit"]["score"]
        assert exp_score == 100.0, (
            f"Expected 100 for mid/senior with senior profile, got {exp_score}"
        )


class TestEdgeCasesExtended:
    """Additional edge case tests."""

    def test_empty_profile_skills(self, mock_profile_path):
        """Job matcher with empty profile skills should not crash."""
        matcher = JobMatcher(mock_profile_path)
        matcher.all_skills = {}
        job = {
            "external_id": "edge_001",
            "title": "Some Role",
            "company": "Test",
            "skills": ["python"],
        }
        score = matcher.score(job)
        assert isinstance(score, float)
        assert 0 <= score <= 100

    def test_swapped_salary_min_max(self, mock_profile_path):
        """Job with salary_min > salary_max should swap gracefully."""
        matcher = JobMatcher(mock_profile_path)
        job = {
            "external_id": "edge_002",
            "title": "Swapped Salary",
            "company": "Test",
            "salary_min": 15000,
            "salary_max": 8000,
            "currency": "USD",
            "skills": ["python"],
        }
        details = matcher.score_detail(job)
        rate_score = details["components"]["rate_fit"]["score"]
        assert isinstance(rate_score, float)
        # After swap, 8000-15000 overlaps profile 5000-10000 → should score >= 50
        assert rate_score >= 50.0, f"Expected >=50 for swapped salary overlap, got {rate_score}"

    def test_no_crash_on_missing_score_fields(self, mock_profile_path):
        """Minimal job with no experience_level, category, remote, etc. still produces all dims."""
        matcher = JobMatcher(mock_profile_path)
        job = {
            "external_id": "minimal_002",
            "title": "Minimal Role",
            "company": "Test",
            "skills": [],
        }
        details = matcher.score_detail(job)
        assert isinstance(details["total_score"], float)
        expected_dims = {
            "skill_overlap",
            "keyword_boost",
            "location_fit",
            "rate_fit",
            "category_fit",
            "experience_fit",
            "behavioral_fit",
            "career_alignment",
        }
        assert set(details["components"].keys()) == expected_dims
