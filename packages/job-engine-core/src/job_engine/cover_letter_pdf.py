"""Cover letter LaTeX wrapper — wraps plain-text cover letters in a professional PDF format."""

import logging
from pathlib import Path

from job_engine.latex_compiler import compile_latex

logger = logging.getLogger(__name__)

_LATEX_SPECIAL_CHARS = {
    "\\": r"\textbackslash{}",
    "&": r"\&",
    "%": r"\%",
    "$": r"\$",
    "#": r"\#",
    "_": r"\_",
    "{": r"\{",
    "}": r"\}",
    "~": r"\textasciitilde{}",
    "^": r"\textasciicircum{}",
}


def latex_escape(text: str) -> str:
    """Escape LaTeX special characters so untrusted text renders literally."""
    return "".join(_LATEX_SPECIAL_CHARS.get(ch, ch) for ch in text)


# --- Template ---------------------------------------------------------------

_COVER_LETTER_TEMPLATE = r"""\documentclass[11pt,a4paper]{moderncv}
\moderncvstyle{banking}
\moderncvcolor{blue}
\usepackage[scale=0.75, top=2.5cm, bottom=2.5cm]{geometry}
\usepackage{fontspec}

\firstname{%%NAME_FIRST%%}
\familyname{%%NAME_LAST%%}
\email{%%EMAIL%%}
\phone{%%PHONE%%}

\begin{document}

\recipient{%%RECIPIENT_COMPANY%%}{%%RECIPIENT_ADDRESS%%}
\date{%%DATE%%}
\opening{Dear Hiring Team,}
\closing{Best regards,}

\makelettertitle

%%BODY%%

\makeletterclosing

\end{document}
"""


def wrap_cover_letter(
    letter_text: str,
    output_dir: str | Path,
    name: str = "cover_letter",
    first_name: str = "",
    last_name: str = "",
    email: str = "",
    phone: str = "",
    company: str = "",
    address: str = "",
) -> str:
    """Wrap a plain-text cover letter in a LaTeX template and compile to PDF.

    Args:
        letter_text: The plain-text cover letter body.
        output_dir: Directory to write files.
        name: Output filename (without extension). Default "cover_letter".
        first_name: Candidate's first name.
        last_name: Candidate's last name.
        email: Candidate's email.
        phone: Candidate's phone number.
        company: Recipient company name.
        address: Recipient address (optional).

    Returns:
        PDF path.

    Raises:
        LatexError: If compilation fails (see ``compile_latex``).
    """
    # Replace placeholders
    # All inserted text is escaped: it comes from the user or the LLM and must
    # never be interpreted as LaTeX (e.g. "%" comments, "\\input{...}").
    tex = _COVER_LETTER_TEMPLATE.replace("%%NAME_FIRST%%", latex_escape(first_name))
    tex = tex.replace("%%NAME_LAST%%", latex_escape(last_name))
    tex = tex.replace("%%EMAIL%%", latex_escape(email))
    tex = tex.replace("%%PHONE%%", latex_escape(phone))
    tex = tex.replace("%%RECIPIENT_COMPANY%%", latex_escape(company))
    tex = tex.replace("%%RECIPIENT_ADDRESS%%", latex_escape(address))
    tex = tex.replace("%%DATE%%", __import__("datetime").datetime.now().strftime("%B %d, %Y"))

    # For moderncv letters, we use \makelettertitle, body, \makeletterclosing
    # Replace the %%BODY%% placeholder in \opening and insert the letter text
    letter_paragraphs = letter_text.strip().split("\n\n")
    formatted_body = "\n\n".join(latex_escape(p.strip()) for p in letter_paragraphs)

    tex = tex.replace("%%BODY%%", formatted_body)

    logger.debug("Cover letter LaTeX:\n%s", tex[:500])

    return compile_latex(tex, output_dir, name=name)
