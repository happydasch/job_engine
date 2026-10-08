"""Prompt constants for LLM integration.

All prompts are separated into their own modules for easy editing and review.
"""

from job_engine._prompts.analysis import ANALYSIS_PROMPT_TEMPLATE
from job_engine._prompts.application_letter import APPLICATION_LETTER_HUMAN_TEMPLATE
from job_engine._prompts.ats_verification import ATS_VERIFICATION_PROMPT
from job_engine._prompts.combined import COMBINED_PROMPT
from job_engine._prompts.cover_letter import (
    _COVER_LETTER_STYLE_RULES,
    COVER_LETTER_PROMPT_TEMPLATE,
)
from job_engine._prompts.cv_draft import CV_DRAFT_PROMPT
from job_engine._prompts.cv_extraction import CV_EXTRACTION_PROMPT
from job_engine._prompts.cv_improve import CV_IMPROVE_PROMPT
from job_engine._prompts.explain_match import EXPLAIN_MATCH_PROMPT_TEMPLATE
from job_engine._prompts.interview import (
    INTERVIEW_QUESTIONS_PROMPT_TEMPLATE,
    PREP_PACK_PROMPT_TEMPLATE,
)
from job_engine._prompts.reviewer import REVIEWER_HUMAN_TEMPLATE, REVIEWER_SYSTEM_PROMPT
from job_engine._prompts.summary import SUMMARY_PROMPT_TEMPLATE
from job_engine._prompts.system import _SYSTEM_PROMPT
from job_engine._sanitize import SANITIZE_FORBIDDANCE

__all__ = [
    "SANITIZE_FORBIDDANCE",
    "_SYSTEM_PROMPT",
    "ANALYSIS_PROMPT_TEMPLATE",
    "EXPLAIN_MATCH_PROMPT_TEMPLATE",
    "SUMMARY_PROMPT_TEMPLATE",
    "PREP_PACK_PROMPT_TEMPLATE",
    "INTERVIEW_QUESTIONS_PROMPT_TEMPLATE",
    "_COVER_LETTER_STYLE_RULES",
    "COVER_LETTER_PROMPT_TEMPLATE",
    "APPLICATION_LETTER_HUMAN_TEMPLATE",
    "COMBINED_PROMPT",
    "CV_EXTRACTION_PROMPT",
    "CV_IMPROVE_PROMPT",
    "REVIEWER_SYSTEM_PROMPT",
    "REVIEWER_HUMAN_TEMPLATE",
    "ATS_VERIFICATION_PROMPT",
    "CV_DRAFT_PROMPT",
]
