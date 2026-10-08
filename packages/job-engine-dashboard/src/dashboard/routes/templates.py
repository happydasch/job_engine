"""Template registration API — upload, test-compile, and manage custom LaTeX templates."""

import logging
import os
import re
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from job_engine.latex_compiler import LatexError, compile_latex
from starlette.datastructures import UploadFile

logger = logging.getLogger(__name__)

router = APIRouter()

TEMPLATES_DIR = Path("data/templates")
TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)

ALLOWED_EXTENSIONS = {".tex", ".cls", ".sty"}


@router.post("/api/templates/register")
async def register_template(request: Request):
    """Upload and register a custom LaTeX template.

    Accepts multipart form with ``file`` and optional ``name`` fields.
    Saves to ``data/templates/<name>``, runs a test compile, and
    returns the compilation result.

    The template must be a valid LaTeX file that compiles with tectonic.
    """
    try:
        form = await request.form()
        file = form.get("file")
        if not isinstance(file, UploadFile):
            raise HTTPException(status_code=400, detail="No file provided")
        name_field = form.get("name", "")
        if not isinstance(name_field, str):
            raise HTTPException(status_code=400, detail="'name' must be a text field")

        filename = file.filename or "template.tex"
        custom_name = name_field.strip() or os.path.splitext(filename)[0]
        # Security: the name becomes a filename — reject path separators / traversal
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", custom_name) or ".." in custom_name:
            raise HTTPException(
                status_code=400,
                detail="Template name may only contain letters, digits, '.', '_' and '-'",
            )

        # Validate extension
        ext = os.path.splitext(filename)[1].lower()
        if ext not in ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported extension '{ext}'. Allowed: {', '.join(ALLOWED_EXTENSIONS)}",
            )

        # Read file content
        content = await file.read()
        if not content or not content.strip():
            raise HTTPException(status_code=400, detail="Empty file")

        text_content = content.decode("utf-8")

        # Validate it's a LaTeX document
        if not any(
            marker in text_content
            for marker in [r"\documentclass", r"\ProvidesClass", r"\ProvidesPackage"]
        ):
            raise HTTPException(
                status_code=400,
                detail="File does not appear to be a valid LaTeX file "
                "(missing \\documentclass, \\ProvidesClass, or \\ProvidesPackage)",
            )

        # Save to templates dir
        save_name = f"{custom_name}{ext}"
        save_path = TEMPLATES_DIR / save_name

        # Avoid overwriting critical templates
        if save_path.exists() and save_name in ("cv.tex", "cover.tex"):
            raise HTTPException(status_code=400, detail="Cannot overwrite built-in templates")

        save_path.write_bytes(content)

        # Test compile (only for full documents, not class/style files)
        test_result = None
        if ext == ".tex":
            try:
                test_result = compile_latex(text_content, TEMPLATES_DIR, name=f"test_{custom_name}")
            except LatexError as exc:
                # Compilation failed — remove the saved template
                save_path.unlink(missing_ok=True)
                raise HTTPException(
                    status_code=400, detail=f"Template failed to compile with tectonic: {exc}"
                ) from exc

        return JSONResponse(
            {
                "status": "ok",
                "name": custom_name,
                "filename": save_name,
                "path": str(save_path),
                "test_compile": bool(test_result),
                "message": f"Template '{custom_name}' registered and verified successfully",
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Template registration failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Template registration failed: {e}")


@router.get("/api/templates")
async def list_templates():
    """List all registered LaTeX templates."""
    templates = []
    for f in sorted(TEMPLATES_DIR.glob("*")):
        if f.is_file() and f.suffix in ALLOWED_EXTENSIONS:
            templates.append(
                {
                    "name": f.stem,
                    "filename": f.name,
                    "extension": f.suffix,
                    "size_bytes": f.stat().st_size,
                }
            )
    return JSONResponse({"templates": templates})
