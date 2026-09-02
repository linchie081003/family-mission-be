import base64

from fastapi import HTTPException

MAX_AVATAR_BYTES = 300_000
MAX_AVATAR_DATA_URL_LENGTH = 400_000


def normalize_avatar_data_url(value: str | None) -> str | None:
    """Validate and return a data-URL avatar string for DB storage."""
    if not value or not value.strip():
        return None
    cleaned = value.strip()
    if not cleaned.startswith("data:image/") or ";base64," not in cleaned:
        return None
    if len(cleaned) > MAX_AVATAR_DATA_URL_LENGTH:
        return None
    return cleaned


def avatar_content_to_data_url(content: bytes, content_type: str | None) -> str:
    if len(content) > MAX_AVATAR_BYTES:
        raise HTTPException(
            status_code=400,
            detail="Foto terlalu besar. Gunakan gambar di bawah 300KB.",
        )
    mime = content_type if content_type in {"image/jpeg", "image/png", "image/webp"} else "image/jpeg"
    encoded = base64.b64encode(content).decode("ascii")
    data_url = f"data:{mime};base64,{encoded}"
    if len(data_url) > MAX_AVATAR_DATA_URL_LENGTH:
        raise HTTPException(status_code=400, detail="Foto terlalu besar setelah diproses.")
    return data_url
