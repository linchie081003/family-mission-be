import re

from fastapi import HTTPException, Request, status

from app.core.config import settings

FAMILY_CODE_PATTERN = re.compile(r"^[A-Z0-9]{4,8}$")


def sanitize_family_code(code: str) -> str:
    normalized = code.strip().upper()
    if not FAMILY_CODE_PATTERN.match(normalized):
        raise HTTPException(status_code=400, detail="Format kode keluarga tidak valid")
    return normalized


def validate_upload(filename: str, content_type: str | None, size: int) -> None:
    allowed_ext = {".jpg", ".jpeg", ".png", ".webp"}
    allowed_mime = {"image/jpeg", "image/png", "image/webp"}
    ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in allowed_ext:
        raise HTTPException(status_code=400, detail="Format file tidak didukung")
    if content_type and content_type not in allowed_mime:
        raise HTTPException(status_code=400, detail="Tipe file tidak didukung")
    if size > settings.max_upload_bytes:
        raise HTTPException(status_code=400, detail="Ukuran file terlalu besar")


def get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"
