from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from graph_explorer_api.dependencies import get_investigation_service
from graph_explorer_api.services.investigation_service import InvestigationService

router = APIRouter(prefix="/api/cases", tags=["investigations"])


@router.post("")
def create_case(
    title: str,
    created_by: str,
    priority: str = "medium",
    service: InvestigationService = Depends(get_investigation_service),
):
    return service.create_case(title, created_by, priority)


@router.get("")
def list_cases(
    service: InvestigationService = Depends(get_investigation_service),
):
    return service.list_cases()


@router.get("/{case_id}")
def get_case(
    case_id: str,
    service: InvestigationService = Depends(get_investigation_service),
):
    case = service.get_case(case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")
    return case


@router.post("/{case_id}/subjects")
def add_subject(
    case_id: str,
    entity_id: str,
    subject_role: str,
    added_by: str,
    service: InvestigationService = Depends(get_investigation_service),
):
    return service.add_subject(case_id, entity_id, subject_role, added_by)


@router.post("/{case_id}/notes")
def add_note(
    case_id: str,
    body: str,
    author_id: str,
    service: InvestigationService = Depends(get_investigation_service),
):
    return service.add_note(case_id, body, author_id)
