PREP_PACK_PROMPT_TEMPLATE = (
    "{SANITIZE_FORBIDDANCE}\n\n"
    "You are a career coach preparing a candidate for a {stage} interview.\n"
    "Generate a comprehensive interview preparation pack. "
    "Return valid JSON with this exact structure:\n"
    "{{\n"
    '  "stage": "{stage}",\n'
    '  "likely_questions": [\n'
    '    {{"question": "...", "type": "technical|behavioral|problem_solving|career", '
    '"prep_tip": "...", "star": {{"situation": "...", "task": "...", '
    '"action": "...", "result": "..."}}}}\n'
    "  ],\n"
    '  "star_mapping": [\n'
    '    {{"category": "leadership|teamwork|achievement|challenge", "story_angle": "...", '
    '"relevant_skill": "...", "suggested_experience": "..."}}\n'
    "  ],\n"
    '  "company_research": {{\n'
    '    "brief": "...",\n'
    '    "key_topics": ["..."],\n'
    '    "questions_to_ask": ["..."]\n'
    "  }},\n"
    '  "consistency_brief": {{\n'
    '    "cv_highlights": ["..."],\n'
    '    "cover_letter_themes": ["..."],\n'
    '    "narrative_arc": "..."\n'
    "  }}\n"
    "}}\n\n"
    "Job Posting:\n{job_context}\n\n"
    "Candidate Profile:\n{cv_context}\n\n"
    "Cover Letter (if available):\n{cover_letter_text}\n"
    "{language_instruction}"
)

INTERVIEW_QUESTIONS_PROMPT_TEMPLATE = (
    "{SANITIZE_FORBIDDANCE}\n\n"
    "Based on this job posting, suggest 5 interview questions "
    "the candidate should prepare for. Mix of technical and behavioral.\n\n"
    "Return a JSON array of objects with keys:\n"
    "- question: the interview question text\n"
    "- type: 'technical', 'behavioral', 'problem_solving', or 'career'\n"
    "- prep_tip: 1-2 sentence hint on how to prepare\n"
    "- star (for behavioral type only): an object with keys\n"
    "  situation, task, action, result\n"
    "  - each a short sentence suggesting a relevant "
    "STAR story angle the candidate can adapt from their experience\n\n"
    "{job_context}\n"
    "{language_instruction}"
)

__all__ = [
    "PREP_PACK_PROMPT_TEMPLATE",
    "INTERVIEW_QUESTIONS_PROMPT_TEMPLATE",
]
