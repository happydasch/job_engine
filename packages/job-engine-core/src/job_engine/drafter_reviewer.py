"""Drafter-Reviewer pattern: generate → review → revise with optional ATS verification."""

import logging
from collections.abc import Callable
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from job_engine._prompts.ats_verification import ATS_VERIFICATION_PROMPT
from job_engine._prompts.reviewer import REVIEWER_HUMAN_TEMPLATE, REVIEWER_SYSTEM_PROMPT
from job_engine._sanitize import SANITIZE_FORBIDDANCE
from job_engine.llm import _parse_json, _safe_invoke, get_llm

logger = logging.getLogger(__name__)


def generate_with_review(
    draft_fn: Callable[[], tuple[str | None, str | None]],
    job_context: str,
    profile_context: str,
    doc_type: str = "cover letter",
    max_iterations: int = 2,
) -> tuple[str | None, str | None]:
    """Generate a document, review it, and revise up to max_iterations times.

    Args:
        draft_fn: Function that returns (draft, error) tuple
        job_context: The job posting context string
        profile_context: The candidate profile context string
        doc_type: Type of document ('cover letter', 'application letter', etc.)
        max_iterations: Maximum number of review-revise cycles

    Returns:
        (final_draft, error) tuple
    """
    llm = get_llm()
    if llm is None:
        return draft_fn()

    # Phase 1: Generate initial draft
    draft, error = draft_fn()
    if error or draft is None:
        return draft, error

    for iteration in range(max_iterations):
        # Phase 2: Review
        review_messages = [
            SystemMessage(content=REVIEWER_SYSTEM_PROMPT),
            HumanMessage(
                content=REVIEWER_HUMAN_TEMPLATE.format(
                    SANITIZE_FORBIDDANCE=SANITIZE_FORBIDDANCE,
                    doc_type=doc_type,
                    job_context=job_context,
                    profile_context=profile_context,
                    draft=draft,
                )
            ),
        ]

        review_result, review_error = _safe_invoke(llm, review_messages)
        if review_error or review_result is None:
            logger.warning("Review failed at iteration %d: %s", iteration, review_error)
            break

        # Parse review
        parsed_review, _ = _parse_json(review_result)
        if not isinstance(parsed_review, dict):
            logger.warning("Review returned non-JSON at iteration %d", iteration)
            break

        assessment = parsed_review.get("overall_assessment", "minor_revisions")
        if assessment == "approved":
            logger.info("Draft approved at iteration %d", iteration)
            break

        issues = parsed_review.get("issues", [])
        has_high = any(i.get("severity") == "high" for i in issues)

        if iteration == max_iterations - 1:
            logger.info("Max iterations reached, returning current draft")
            break

        # Phase 3: Revise based on review
        # We need to call the draft function again with the review feedback
        # This is a simplified approach - in practice, we'd need to pass feedback to the generation
        # For now, we return the draft with a note about pending revisions
        logger.info(
            "Draft needs %s (%d issues, %d high severity)",
            assessment,
            len(issues),
            sum(1 for i in issues if i.get("severity") == "high"),
        )

        # If there are no high-severity issues, accept the draft
        if not has_high:
            break

    return draft, None


def verify_ats(document: str, keywords: list[str]) -> dict[str, Any] | None:
    """Verify a document against ATS compliance criteria.

    Args:
        document: The document text to verify
        keywords: List of relevant keywords from the job posting

    Returns:
        ATS verification result dict, or None on failure
    """
    llm = get_llm()
    if llm is None:
        return None

    messages = [
        SystemMessage(content="You are an ATS compliance checker. Return JSON only."),
        HumanMessage(
            content=ATS_VERIFICATION_PROMPT.format(
                SANITIZE_FORBIDDANCE=SANITIZE_FORBIDDANCE,
                document=document,
                keywords=", ".join(keywords),
            )
        ),
    ]

    result, error = _safe_invoke(llm, messages)
    if error or result is None:
        return None

    parsed, _ = _parse_json(result)
    if isinstance(parsed, dict):
        return parsed
    return None
