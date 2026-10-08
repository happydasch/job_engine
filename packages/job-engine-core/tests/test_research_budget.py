"""Tests for job_engine.research_budget — depth validation."""

import pytest
from job_engine import research_budget
from job_engine.research_budget import ResearchBudget, ResearchDepth


@pytest.mark.parametrize(
    ("depth", "limit"), [("none", 0), ("BASIC", 3), (ResearchDepth.THOROUGH, 10)]
)
def test_valid_depths(depth, limit):
    assert ResearchBudget(depth).limit == limit


@pytest.mark.parametrize("depth", ["deep", "", None])
def test_invalid_depth_raises(depth):
    with pytest.raises(ValueError, match="Unknown research depth"):
        ResearchBudget(depth)  # type: ignore[arg-type]


class _Settings:
    def __init__(self, data):
        self._data = data

    def load(self):
        return self._data


def test_from_settings_defaults_to_basic_when_key_absent(monkeypatch):
    monkeypatch.setattr("job_engine.config.get_app_settings", lambda: _Settings({}))

    assert research_budget.get_research_budget_from_settings().depth is ResearchDepth.BASIC


def test_from_settings_invalid_value_raises(monkeypatch):
    monkeypatch.setattr(
        "job_engine.config.get_app_settings", lambda: _Settings({"research_depth": "lots"})
    )

    with pytest.raises(ValueError):
        research_budget.get_research_budget_from_settings()
