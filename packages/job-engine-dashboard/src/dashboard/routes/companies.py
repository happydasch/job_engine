from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse
from job_engine.database import get_sync_engine as get_engine
from job_engine.models import Company, Job
from sqlalchemy.orm import Session, joinedload

from dashboard.common import job_to_dict, load_companies_from_db

router = APIRouter()


@router.get("/api/companies", response_class=JSONResponse)
async def api_companies(
    sort_by: str = Query("name", description="Sort field"),
    sort_order: str = Query("asc", description="Sort direction"),
    q: str = Query("", description="Free-text search"),
    job_id: str = Query("", description="Filter to company for a specific job (by external_id)"),
):
    """JSON API for all companies."""
    return JSONResponse(load_companies_from_db(sort_by, sort_order, q, job_id))


@router.get("/api/companies/{company_id}", response_class=JSONResponse)
async def api_company_detail(company_id: int):
    """JSON API: single company detail with its jobs."""
    engine = get_engine()
    with Session(engine) as session:
        company = session.query(Company).filter(Company.id == company_id).first()
        if company is None:
            raise HTTPException(status_code=404, detail="Company not found")
        jobs = (
            session.query(Job)
            .filter(Job.company_id == company_id)
            .options(joinedload(Job.company_rel), joinedload(Job.applications))
            .order_by(Job.updated_at.desc())
            .all()
        )

        company_dict = {
            "id": company.id,
            "name": company.name,
            "url": company.url,
            "logo_url": company.logo_url,
            "industry": company.industry,
            "size_range": company.size_range,
            "headquarters": company.headquarters,
            "founded_year": company.founded_year,
            "description": company.description,
            "linkedin_url": company.linkedin_url,
            "job_count": len(jobs),
            "created_at": company.created_at.isoformat() if company.created_at else None,
            "updated_at": company.updated_at.isoformat() if company.updated_at else None,
            "jobs": [job_to_dict(j) for j in jobs],
        }
    return JSONResponse(company_dict)
