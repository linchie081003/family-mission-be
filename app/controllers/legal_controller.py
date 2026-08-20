"""Controller: legal documents."""

from fastapi import APIRouter

from app.schemas import LegalDocumentResponse
from app.services.legal_service import get_privacy_document, get_terms_document

router = APIRouter(prefix="/legal", tags=["legal"])


@router.get("/privacy", response_model=LegalDocumentResponse)
async def privacy_policy():
    return LegalDocumentResponse(**get_privacy_document())


@router.get("/terms", response_model=LegalDocumentResponse)
async def terms_of_service():
    return LegalDocumentResponse(**get_terms_document())
