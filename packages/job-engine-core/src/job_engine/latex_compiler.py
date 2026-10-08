"""
LaTeX compilation engine — builds PDFs from .tex templates using tectonic.

Provides:
- compile_latex() — write .tex → run tectonic → return PDF path
- verify_cv() — check CV is exactly 2 pages
- verify_cover_letter() — check cover letter is exactly 1 page
- extract_text_from_pdf() — pdftotext wrapper
- ats_verify_pdf() — PDF-specific ATS checks
"""

import logging
import re
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


class LatexError(RuntimeError):
    """Raised when a LaTeX/PDF tool (tectonic, pdftotext) is missing or fails."""


# --- Compilation -----------------------------------------------------------


def compile_latex(tex_content: str, output_dir: str | Path, name: str = "output") -> str:
    """Write ``tex_content`` to a .tex file and compile it with tectonic.

    Args:
        tex_content: Complete LaTeX document source.
        output_dir: Directory to write the .tex and .pdf into.
        name: Base filename (without extension). Defaults to "output".

    Returns:
        Absolute path to the generated PDF.

    Raises:
        LatexError: If tectonic is missing, times out, fails, or produces no PDF.
        OSError: If the .tex file cannot be written.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    tex_path = output_dir / f"{name}.tex"
    pdf_path = output_dir / f"{name}.pdf"

    tex_path.write_text(tex_content, encoding="utf-8")

    try:
        result = subprocess.run(
            ["tectonic", str(tex_path)],
            capture_output=True,
            text=True,
            timeout=120,
        )
    except FileNotFoundError as e:
        raise LatexError("tectonic not found on PATH. Install via: brew install tectonic") from e
    except subprocess.TimeoutExpired as e:
        raise LatexError(f"tectonic compilation timed out for {tex_path}") from e

    if result.returncode != 0:
        raise LatexError(
            f"tectonic compilation failed for {tex_path}\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )

    # tectonic writes the PDF next to the .tex by default
    if not pdf_path.exists():
        # Try with .pdf extension
        candidates = list(output_dir.glob("*.pdf"))
        if candidates:
            pdf_path = candidates[0]
        else:
            raise LatexError(f"tectonic succeeded but no PDF found in {output_dir}")

    logger.info("Compiled %s -> %s (%.1f KiB)", tex_path, pdf_path, pdf_path.stat().st_size / 1024)
    return str(pdf_path.resolve())


# --- PDF verification -------------------------------------------------------


def get_pdf_page_count(pdf_path: str | Path) -> int:
    """Return page count of a PDF using pdftotext and counting form feeds.

    Raises:
        LatexError: If pdftotext is missing or fails.
    """
    # Each page ends with a form feed character (\x0c)
    count = _extract_text_raw(pdf_path).count("\x0c")
    return max(count, 1)


def verify_cv(pdf_path: str | Path) -> dict:
    """Verify a CV PDF meets formatting standards.

    Checks:
    - Exactly 2 pages
    - No orphaned section titles at page bottom

    Returns dict with keys: ok (bool), pages (int), issues (list[str]).
    """
    issues: list[str] = []
    pages = get_pdf_page_count(pdf_path)
    if pages != 2:
        issues.append(f"CV is {pages} pages — expected exactly 2")

    # Check for orphaned section titles (a section title at the very end of a page)
    text = _extract_text_raw(pdf_path)
    if text.strip():
        page_boundaries = text.split("\x0c")
        for i, page in enumerate(page_boundaries):
            stripped = page.strip()
            if not stripped:
                continue
            last_line = stripped.split("\n")[-1].strip()
            # Check if last line looks like a section title (short, starts with capital, no period)
            if (
                last_line
                and len(last_line) < 40
                and last_line[0].isupper()
                and not last_line.endswith(".")
            ):
                # Check it's not already followed by content on the next page
                if i + 1 < len(page_boundaries):
                    next_stripped = page_boundaries[i + 1].strip()
                    if not next_stripped or len(next_stripped.split("\n")) < 2:
                        issues.append(f"Possible orphaned title on page {i + 1}: '{last_line}'")

    return {"ok": len(issues) == 0, "pages": pages, "issues": issues}


def verify_cover_letter(pdf_path: str | Path) -> dict:
    """Verify a cover letter PDF — expected exactly 1 page.

    Returns dict with keys: ok (bool), pages (int), issues (list[str]).
    """
    issues: list[str] = []
    pages = get_pdf_page_count(pdf_path)
    if pages != 1:
        issues.append(f"Cover letter is {pages} pages — expected exactly 1")

    return {"ok": len(issues) == 0, "pages": pages, "issues": issues}


# --- Text extraction --------------------------------------------------------


def _extract_text_raw(pdf_path: str | Path) -> str:
    """Extract raw text from a PDF via pdftotext, preserving page breaks.

    Raises:
        LatexError: If pdftotext is missing, times out, or fails.
    """
    try:
        result = subprocess.run(
            ["pdftotext", str(pdf_path), "-"],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except FileNotFoundError as e:
        raise LatexError("pdftotext not found on PATH. Install via: brew install poppler") from e
    except subprocess.TimeoutExpired as e:
        raise LatexError(f"pdftotext timed out for {pdf_path}") from e
    if result.returncode != 0:
        raise LatexError(f"pdftotext exit code {result.returncode}: {result.stderr}")
    return result.stdout


def extract_text_from_pdf(pdf_path: str | Path) -> str:
    """Extract readable text from a PDF, collapsing form feeds."""
    raw = _extract_text_raw(pdf_path)
    return raw.replace("\x0c", "\n--- PAGE BREAK ---\n")


# --- ATS verification for PDF ------------------------------------------------


def ats_verify_pdf(pdf_path: str | Path, job_keywords: list[str]) -> dict:
    """Run ATS compatibility checks against a compiled PDF.

    Checks:
    - Text layer exists (PDF is not scanned image)
    - Key technical terms from the job survive extraction
    - Contact details (email, phone) are present and machine-readable

    Returns dict with keys: has_text_layer (bool), keyword_coverage_pct (float),
    has_contact (bool), issues (list[str]).
    """
    issues: list[str] = []
    text = _extract_text_raw(pdf_path)

    if not text.strip():
        return {
            "has_text_layer": False,
            "keyword_coverage_pct": 0.0,
            "has_contact": False,
            "issues": ["PDF has no extractable text layer — may be a scanned image"],
        }

    has_text_layer = bool(text.strip())

    # Check for contact info
    has_email = bool(re.search(r"[\w.+-]+@[\w-]+\.[\w.+-]+", text))
    has_phone = bool(re.search(r"\+?\d[\d\s\-().]{7,}\d", text))
    has_contact = has_email or has_phone

    # Keyword coverage (case-insensitive)
    lower_text = text.lower()
    matched_keywords = [kw for kw in job_keywords if kw.lower() in lower_text]
    coverage = len(matched_keywords) / max(len(job_keywords), 1) * 100

    return {
        "has_text_layer": has_text_layer,
        "keyword_coverage_pct": round(coverage, 1),
        "keywords_matched": matched_keywords,
        "has_contact": has_contact,
        "has_email": has_email,
        "has_phone": has_phone,
        "issues": issues,
    }
