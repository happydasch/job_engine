"""ATS (Applicant Tracking System) verification prompt."""

ATS_VERIFICATION_PROMPT = """\
{SANITIZE_FORBIDDANCE}

You are an ATS (Applicant Tracking System) compliance checker. Verify the following \
document against these criteria:

1. **Word count**: Cover letters should be 250-400 words. CVs should be 1-2 pages.
2. **Keyword coverage**: Does the document include relevant keywords from the job posting?
3. **Contact details**: Are email and phone number present?
4. **Formatting**: Is the document plain text friendly (no tables, columns, \
or special characters that ATS parsers might miss)?
5. **Section headers**: Are standard section headers used (Experience, Education, Skills)?

## Document
{document}

## Job Posting Keywords
{keywords}

## Output Format
Return a JSON object with this structure:
{{
    "ats_score": 0-100,
    "word_count": number,
    "issues": [
        {{"category": "formatting"|"keywords"|"length"|"structure", "description": "..."}}
    ],
    "recommendations": ["..."],
    "passes_ats": true|false
}}
"""
