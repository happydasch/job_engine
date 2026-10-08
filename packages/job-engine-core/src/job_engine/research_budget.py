"""Bounded research budget for LLM evaluations.

Controls how many web queries an LLM evaluation can make, based on the
configured research_depth setting.
"""

import logging
from enum import StrEnum

logger = logging.getLogger(__name__)


class ResearchDepth(StrEnum):
    """Research depth levels controlling web query budget."""

    NONE = "none"  # 0 web queries
    BASIC = "basic"  # max 3 web queries
    THOROUGH = "thorough"  # max 10 web queries


_DEPTH_LIMITS = {
    ResearchDepth.NONE: 0,
    ResearchDepth.BASIC: 3,
    ResearchDepth.THOROUGH: 10,
}


class ResearchBudget:
    """Tracks and enforces a web query budget for a single evaluation.

    Usage:
        budget = ResearchBudget("basic")
        while budget.can_query():
            budget.record_query("https://...")
            # ... make query ...
    """

    def __init__(self, depth: str | ResearchDepth = "basic") -> None:
        if not isinstance(depth, ResearchDepth):
            valid = ", ".join(d.value for d in ResearchDepth)
            if not isinstance(depth, str) or depth.lower() not in {d.value for d in ResearchDepth}:
                raise ValueError(f"Unknown research depth {depth!r}. Expected one of: {valid}")
            depth = ResearchDepth(depth.lower())
        self._depth = depth
        self._limit = _DEPTH_LIMITS[depth]
        self._queries_made: list[str] = []

    @property
    def depth(self) -> ResearchDepth:
        return self._depth

    @property
    def limit(self) -> int:
        return self._limit

    @property
    def queries_made(self) -> list[str]:
        return list(self._queries_made)

    @property
    def queries_remaining(self) -> int:
        return max(0, self._limit - len(self._queries_made))

    def can_query(self) -> bool:
        """Return True if another query is within budget."""
        return len(self._queries_made) < self._limit

    def record_query(self, url: str) -> None:
        """Record that a query was made, decrementing the budget.

        Raises:
            RuntimeError: If the budget is exhausted.
        """
        if not self.can_query():
            raise RuntimeError(
                f"Research budget exhausted ({self._limit}/{self._limit} queries used)"
            )
        self._queries_made.append(url)
        logger.debug(
            "Research query recorded: %s (%d/%d)", url, len(self._queries_made), self._limit
        )

    def reset(self) -> None:
        """Reset the query counter for a new evaluation."""
        self._queries_made.clear()

    def __repr__(self) -> str:
        used = len(self._queries_made)
        return f"<ResearchBudget depth={self._depth.value} used={used}/{self._limit}>"


def get_research_budget_from_settings() -> ResearchBudget:
    """Create a ResearchBudget based on the current app settings.

    Reads the optional 'research_depth' key from app_settings.yaml
    ('basic' when the key is absent). An invalid value raises ValueError.
    """
    from job_engine.config import get_app_settings

    depth = get_app_settings().load().get("research_depth", "basic")
    return ResearchBudget(depth)
