EXPLAIN_MATCH_PROMPT_TEMPLATE = (
    "{SANITIZE_FORBIDDANCE}\n\n"
    "Explain how well this job matches the candidate's profile.\n\n"
    "{job_context}\n\n"
    "{profile_notes}\n\n"
    "Return a JSON object with:\n"
    "- summary: one-sentence overall assessment\n"
    "- strengths: list of reasons this is a good fit\n"
    "- gaps: list of potential mismatches or missing skills\n"
    "- recommendation: 'strong_match', 'good_match', 'possible', or 'weak_match'\n"
    "{language_instruction}"
)
