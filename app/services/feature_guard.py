from typing import Annotated

from fastapi import Depends, HTTPException

from app.core.auth import get_current_family
from app.models.models import Family

FEATURE_LABELS = {
    "quiz": "Quiz",
    "chat": "Chat",
    "agenda": "Agenda Keluarga",
}


def require_feature(feature: str):
    async def _guard(family: Annotated[Family, Depends(get_current_family)]) -> Family:
        enabled = getattr(family, f"{feature}_enabled", False)
        if not enabled:
            label = FEATURE_LABELS.get(feature, feature)
            raise HTTPException(status_code=403, detail=f"Fitur {label} belum diaktifkan untuk keluarga ini")
        return family

    return _guard


def assert_feature_enabled(family: Family, feature: str) -> None:
    enabled = getattr(family, f"{feature}_enabled", False)
    if not enabled:
        label = FEATURE_LABELS.get(feature, feature)
        raise HTTPException(status_code=403, detail=f"Fitur {label} belum diaktifkan untuk keluarga ini")
