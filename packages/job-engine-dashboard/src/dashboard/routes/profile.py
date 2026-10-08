"""Profile configuration API routes — edit my_profile.yaml from the dashboard popup."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from io import BytesIO
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from job_engine.config import get_profile_config
from starlette.datastructures import UploadFile

logger = logging.getLogger(__name__)


def _extract_pdf_text(content: bytes) -> str:
    """Extract text from a PDF file content using available backends.

    Tries PyMuPDF (fitz), then pdfminer, then pypdf as fallbacks.
    Returns empty string if no PDF library is available.
    """
    text = ""
    # Try PyMuPDF (fitz) first
    try:
        import fitz  # type: ignore[import-untyped]

        doc = fitz.open(stream=content, filetype="pdf")
        for page in doc:
            page_text = page.get_text()
            if not isinstance(page_text, str):
                raise TypeError(f"fitz get_text() returned {type(page_text).__name__}")
            text += page_text
        doc.close()
        if text.strip():
            return text
    except ImportError:
        pass
    except Exception as exc:
        logger.warning("PDF extraction with fitz failed: %s", exc)

    # Try pdfminer.six
    try:
        from pdfminer.high_level import extract_text  # type: ignore[import-untyped]

        text = extract_text(BytesIO(content))
        if text.strip():
            return text
    except ImportError:
        pass
    except Exception as exc:
        logger.warning("PDF extraction with pdfminer failed: %s", exc)

    # Try pypdf as last resort
    try:
        from pypdf import PdfReader  # type: ignore[import-untyped]

        reader = PdfReader(BytesIO(content))
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
        if text.strip():
            return text
    except ImportError:
        pass
    except Exception as exc:
        logger.warning("PDF extraction with pypdf failed: %s", exc)

    return text


def _sanitize_extracted(extracted: dict[str, Any]) -> dict[str, Any]:
    """Sanitize and validate extracted CV fields before merging into profile.

    Ensures type correctness for all fields the LLM extraction returns.
    """
    result: dict[str, Any] = {}
    for k, v in extracted.items():
        if k == "name" and isinstance(v, str):
            result[k] = v.strip()
        elif k == "role" and isinstance(v, str):
            result[k] = v.strip()
        elif k == "experience_years":
            try:
                result[k] = int(v)
            except (TypeError, ValueError):
                result[k] = None
        elif k == "currency" and isinstance(v, str):
            c = v.strip().upper()
            result[k] = c[:3] if c else None
        elif k == "rate" and isinstance(v, dict):
            rate: dict[str, Any] = {}
            min_m = v.get("min_monthly")
            max_m = v.get("max_monthly")
            if min_m is not None:
                rate["min_monthly"] = _safe_number(min_m)
            if max_m is not None:
                rate["max_monthly"] = _safe_number(max_m)
            if rate:
                result[k] = rate
            else:
                result[k] = None
        elif k == "skills" and isinstance(v, dict):
            cleaned: dict[str, list[str]] = {}
            for cat, skills in v.items():
                if isinstance(cat, str) and isinstance(skills, list):
                    cleaned[cat] = [s.strip() for s in skills if isinstance(s, str) and s.strip()]
            if cleaned:
                result[k] = cleaned
        elif k in ("boosted_keywords", "career_goals", "behavioral_keywords") and isinstance(
            v, list
        ):
            result[k] = [s.strip() for s in v if isinstance(s, str) and s.strip()]
        elif k in ("experience", "projects") and isinstance(v, list):
            cleaned_exp = []
            for item in v:
                if isinstance(item, dict):
                    name = item.get("name", "")
                    desc = item.get("description", "")
                    cleaned_exp.append(
                        {
                            "name": str(name).strip() if name else "",
                            "description": str(desc).strip() if desc else "",
                        }
                    )
            if cleaned_exp:
                result[k] = cleaned_exp
        else:
            # Pass through unchanged for unknown fields
            result[k] = v
    # After the loop, if both rate dict and top-level currency exist,
    # ensure currency is inside the rate dict (preferred location)
    if (
        result.get("currency")
        and isinstance(result.get("rate"), dict)
        and "currency" not in result["rate"]
    ):
        result["rate"]["currency"] = result["currency"]
    return result


def _safe_number(val: Any) -> int | float | None:
    """Convert a value to a number, returning None on failure."""
    if isinstance(val, (int, float)):
        return val
    if isinstance(val, str):
        try:
            return int(val)
        except ValueError:
            try:
                return float(val)
            except ValueError:
                return None
    return None


router = APIRouter()

# Profile sections editable via the API. ``update_profile_section`` additionally
# accepts "currency"; ``append_profile_items`` uses this set as-is.
_KNOWN_SECTIONS = frozenset(
    {
        "basic",
        "name",
        "role",
        "experience_years",
        "rate",
        "skills",
        "critical_categories",
        "boosted_keywords",
        "experience",
        "behavioral_keywords",
        "career_goals",
        "exchange_rates",
    }
)


@router.get("/api/currencies")
async def get_currencies():
    """Return the full ISO 4217 currency list for dropdown selectors."""
    from job_engine.currency_converter import get_all_currencies

    return JSONResponse(content={"currencies": get_all_currencies()})


@router.post("/api/profile/upload-cv")
async def upload_cv(request: Request):
    """Upload a CV (text or PDF) and extract its text.

    Accepts multipart form data with a ``file`` field.
    Extracts text from PDF (or uses plain text) and returns it.
    No LLM analysis is performed — use /api/profile/parse-cv-text for that.
    """
    try:
        form = await request.form()
        file = form.get("file")
        if not isinstance(file, UploadFile):
            logger.warning("Upload CV: no file provided")
            raise HTTPException(status_code=400, detail="No file provided")

        # Read file content
        filename = file.filename or ""
        content = await file.read()

        # Extract text from PDF or plain text
        if filename.lower().endswith(".pdf"):
            text = _extract_pdf_text(content)
        else:
            text = content.decode("utf-8", errors="replace")

        if not text or not text.strip():
            logger.warning(
                "Upload CV: could not extract text from file '%s' (first 100 bytes: %r)",
                filename,
                content[:100],
            )
            raise HTTPException(status_code=400, detail="Could not extract text from file")

        # Truncate very long CVs
        text = text[:15000]

        return JSONResponse(
            content={
                "status": "ok",
                "text": text,
            }
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Upload CV: unexpected error")
        raise HTTPException(status_code=500, detail=f"CV upload failed: {exc}")


@router.post("/api/profile/improve-cv")
async def improve_cv(request: Request):
    """Improve/optimize CV text using the LLM.

    Accepts JSON body: ``{\"text\": \"...\"}`` — the raw CV text to improve.
    Returns improved CV text with summary and list of changes.
    """
    from job_engine.llm import improve_cv as llm_improve_cv

    try:
        body = await request.json()
        text = body.get("text", "")

        if not text or not text.strip():
            raise HTTPException(status_code=400, detail="No text provided")

        # Truncate very long CVs
        text = text[:15000]

        # Load current profile for context
        cfg = get_profile_config()
        profile = cfg.load()

        # Call LLM to improve CV
        result = llm_improve_cv(text, profile)
        if result is None:
            raise HTTPException(
                status_code=502,
                detail="CV improvement failed. Ensure an LLM API key is set in Settings.",
            )

        return JSONResponse(
            content={
                "status": "ok",
                "improved_text": result.get("improved_text", ""),
                "summary": result.get("summary", ""),
                "changes": result.get("changes", []),
            }
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Improve CV: unexpected error")
        raise HTTPException(status_code=500, detail=f"CV improvement failed: {exc}")


@router.post("/api/profile/parse-cv-text")
async def parse_cv_text(request: Request):
    """Parse CV text (already extracted) and populate profile using LLM.

    Accepts JSON body: ``{\"text\": \"...\"}`` — the raw CV text.
    Use this after the user has reviewed/edited text extracted from a file.
    """
    from job_engine.llm import extract_profile_from_cv as llm_extract

    try:
        body = await request.json()
        text = body.get("text", "")

        if not text or not text.strip():
            logger.warning("Parse CV text: no text provided")
            raise HTTPException(status_code=400, detail="No text provided")

        # Truncate very long CVs
        text = text[:15000]

        # Call LLM to extract profile
        extracted = llm_extract(text)
        if extracted is None:
            logger.error(
                "Parse CV text: LLM extraction returned None - check LLM API key in Settings"
            )
            raise HTTPException(
                status_code=502,
                detail="LLM extraction failed. Ensure an LLM API key is set in Settings.",
            )

        # Merge extracted data into the profile
        cfg = get_profile_config()
        profile = cfg.load()

        # Sanitize and validate extracted fields before merging
        extracted = _sanitize_extracted(extracted)

        # Merge section by section
        if extracted.get("name"):
            profile["name"] = extracted["name"]
        if extracted.get("role"):
            profile["role"] = extracted["role"]
        if extracted.get("experience_years") is not None:
            profile["experience_years"] = extracted["experience_years"]
        if extracted.get("currency"):
            profile["currency"] = extracted["currency"]
        if extracted.get("rate"):
            profile["rate"] = extracted["rate"]
        # After merging, promote top-level currency into rate dict if missing
        if profile.get("currency") and "currency" not in profile.get("rate", {}):
            profile.setdefault("rate", {})["currency"] = profile["currency"]
        if extracted.get("skills"):
            existing = profile.get("skills", {})
            for cat, skills in extracted["skills"].items():
                if cat not in existing:
                    existing[cat] = skills
                else:
                    existing_set = set(existing[cat])
                    for s in skills:
                        if s not in existing_set:
                            existing[cat].append(s)
                            existing_set.add(s)
            profile["skills"] = existing
        if extracted.get("boosted_keywords"):
            existing_kw = set(profile.get("boosted_keywords", []))
            for kw in extracted["boosted_keywords"]:
                if kw not in existing_kw:
                    profile.setdefault("boosted_keywords", []).append(kw)
                    existing_kw.add(kw)
        extracted_experience = extracted.get("experience") or extracted.get("projects")
        if extracted_experience:
            existing_exp = {p.get("name") for p in profile.get("experience", []) if p.get("name")}
            for exp in extracted_experience:
                if exp.get("name") and exp["name"] not in existing_exp:
                    profile.setdefault("experience", []).append(exp)
                    existing_exp.add(exp["name"])

        cfg.save(profile)

        return JSONResponse(
            content={
                "status": "ok",
                "message": "Profile extracted from CV text and merged",
                "extracted": extracted,
                "profile": profile,
            }
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Parse CV text: unexpected error")
        raise HTTPException(status_code=500, detail=f"CV text parsing failed: {exc}")


@router.get("/api/exchange-rates")
async def get_exchange_rates():
    """Return cached exchange rates + profile currency for frontend conversion display."""
    from job_engine.currency_converter import get_rates

    profile = get_profile_config().load()
    profile_currency = (
        profile.get("rate", {}).get("currency") or profile.get("currency") or "USD"
    ).upper()
    rates_obj = get_rates()

    if rates_obj is None:
        # Fall back to profile's static rates if backend rates are unavailable
        static_rates = profile.get("exchange_rates", {}).get("rates", {})
        return JSONResponse(
            content={
                "base": "USD",
                "profile_currency": profile_currency,
                "rates": static_rates,
                "source": "profile",
                "fetched_at": None,
            }
        )

    return JSONResponse(
        content={
            "base": rates_obj.base,
            "profile_currency": profile_currency,
            "rates": rates_obj.rates,
            "source": "live",
            "fetched_at": (
                datetime.fromtimestamp(rates_obj.fetched_at, tz=UTC).isoformat()
                if rates_obj.fetched_at
                else None
            ),
        }
    )


@router.post("/api/profile/refresh-rates")
async def refresh_exchange_rates():
    """Force-refresh exchange rates from the API."""
    from job_engine.currency_converter import refresh_rates

    success = refresh_rates()
    if success:
        return JSONResponse(content={"status": "ok", "message": "Exchange rates refreshed"})
    return JSONResponse(
        content={"status": "error", "message": "Failed to refresh exchange rates"},
        status_code=502,
    )


@router.get("/api/profile/data")
async def get_profile_data():
    """Return the full profile as JSON."""
    profile = get_profile_config().load()
    return JSONResponse(content=profile)


@router.patch("/api/profile")
async def update_profile_section(request: Request):
    """Update a single section of the profile YAML file.

    Expects JSON body: ``{"section": "...", "values": ...}``

    Returns the updated full profile on success.
    """
    body = await request.json()
    section = body.get("section")
    values = body.get("values")

    if not section:
        raise HTTPException(status_code=400, detail="Missing 'section' field")
    if values is None:
        raise HTTPException(status_code=400, detail="Missing 'values' field")

    # Whitelist known sections ("currency" is editable here but not via append)
    known_sections = _KNOWN_SECTIONS | {"currency"}

    if section not in known_sections:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown section '{section}'. Allowed: {', '.join(sorted(known_sections))}",
        )

    # Validation
    errors = []
    if section == "experience_years":
        if not isinstance(values, int):
            try:
                values = int(values)
            except (ValueError, TypeError):
                errors.append("experience_years must be an integer")
        if isinstance(values, int):
            if values < 0:
                errors.append("experience_years must be >= 0")
            if values > 50:
                errors.append("experience_years must be <= 50")

    if section == "rate":
        if isinstance(values, dict):
            min_v = values.get("min_monthly", 0)
            max_v = values.get("max_monthly", 0)
            if not isinstance(min_v, (int, float)) or min_v < 0:
                errors.append("min_monthly must be a non-negative number")
            if not isinstance(max_v, (int, float)) or max_v < 0:
                errors.append("max_monthly must be a non-negative number")
            if (
                isinstance(min_v, (int, float))
                and isinstance(max_v, (int, float))
                and max_v < min_v
            ):
                errors.append("max_monthly must be >= min_monthly")
            # currency is optional, just validate format if present
            currency_v = values.get("currency")
            if currency_v is not None and (not isinstance(currency_v, str) or len(currency_v) > 3):
                errors.append("currency must be a 3-letter code")
        else:
            errors.append("rate must be an object with min_monthly and max_monthly")

    if section == "basic" and not isinstance(values, dict):
        errors.append("basic values must be an object")

    if errors:
        raise HTTPException(status_code=400, detail="; ".join(errors))

    cfg = get_profile_config()
    try:
        if section == "basic" and isinstance(values, dict):
            # Unpack "basic" into individual top-level keys
            data = cfg.load()
            for key in ("name", "role", "experience_years"):
                if key in values:
                    data[key] = values[key]
            # Rate fields — include currency inside the rate dict
            if "min_monthly" in values or "max_monthly" in values or "currency" in values:
                rate = data.get("rate", {})
                if "min_monthly" in values:
                    rate["min_monthly"] = values["min_monthly"]
                if "max_monthly" in values:
                    rate["max_monthly"] = values["max_monthly"]
                if "currency" in values:
                    rate["currency"] = values["currency"]
                data["rate"] = rate
            # Preferences fields — store at root level
            for key in ("remote_only", "preferred_locations", "excluded_companies"):
                if key in values:
                    data[key] = values[key]
            cfg.save(data)
            updated = data
        elif section == "currency":
            # Write currency inside the rate dict (backward compat for SettingsPanel mirror)
            data = cfg.load()
            data.setdefault("rate", {})["currency"] = values
            cfg.save(data)
            updated = data
        else:
            # Resolve taxonomy-aware values through TaxonomyResolver
            if section in ("boosted_keywords", "behavioral_keywords", "career_goals"):
                from job_engine.taxonomy import TaxonomyResolver

                _resolver = TaxonomyResolver()
                category_map = {
                    "boosted_keywords": "boosted",
                    "behavioral_keywords": "behavioral",
                    "career_goals": "career",
                }
                cat = category_map[section]
                if isinstance(values, list):
                    values = _resolver.resolve_many(values, cat)
            updated = cfg.update_section(section, values)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to save: {exc}")

    return JSONResponse(
        content={
            "status": "ok",
            "section": section,
            "profile": updated,
        }
    )


@router.post("/api/profile/append-items")
async def append_profile_items(request: Request):
    """Append items to a profile section without replacing the whole section.

    Expects JSON body::

        {"section": "skills", "items": ["python"], "sub_key": "ai_extracted"}
        {"section": "boosted_keywords", "items": ["fintech"]}

    - For dict-type sections (``skills``), ``sub_key`` is required and items are appended
      to the list at that sub-key.
    - For array-type sections (``boosted_keywords``, ``career_goals``, ``behavioral_keywords``),
      items are appended directly.
    - Duplicates are silently skipped.

    Returns the full updated profile.
    """
    body = await request.json()
    section = body.get("section")
    items = body.get("items", [])
    sub_key = body.get("sub_key")

    if not section:
        raise HTTPException(status_code=400, detail="Missing 'section' field")
    if not items or not isinstance(items, list):
        raise HTTPException(status_code=400, detail="'items' must be a non-empty array")

    known_sections = _KNOWN_SECTIONS
    _array_sections = {"boosted_keywords", "career_goals", "behavioral_keywords"}
    _dict_sections = {"skills"}

    if section not in known_sections:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown section '{section}'. Allowed: {', '.join(sorted(known_sections))}",
        )

    cfg = get_profile_config()
    try:
        data = cfg.load()
        normalized = [s.strip() for s in items if isinstance(s, str) and s.strip()]

        if section in _dict_sections:
            if not sub_key:
                raise HTTPException(
                    status_code=400,
                    detail=f"'sub_key' is required for dict-type section '{section}'",
                )
            sub = data.setdefault(section, {}).setdefault(sub_key, [])
            existing_lower = {s.lower() for s in sub}
            added = []
            for item in normalized:
                if item.lower() not in existing_lower:
                    sub.append(item)
                    existing_lower.add(item.lower())
                    added.append(item)
            if not added:
                return JSONResponse(
                    content={
                        "status": "ok",
                        "section": section,
                        "added": [],
                        "profile": data,
                    }
                )
        elif section in _array_sections:
            existing_lower = {s.lower() for s in data.get(section, [])}
            items_list = data.setdefault(section, [])
            added = []
            for item in normalized:
                if item.lower() not in existing_lower:
                    items_list.append(item)
                    existing_lower.add(item.lower())
                    added.append(item)
        else:
            raise HTTPException(
                status_code=400, detail=f"Section '{section}' does not support append"
            )

        cfg.save(data)
        return JSONResponse(
            content={
                "status": "ok",
                "section": section,
                "added": added,
                "profile": data,
            }
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Append profile items: unexpected error")
        raise HTTPException(status_code=500, detail=f"Failed to append: {exc}")
