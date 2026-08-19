from fastapi import HTTPException

MAX_IMAGE_DATA_URL_LENGTH = 400_000


def normalize_image_data_url(value: str | None, *, required: bool = False) -> str | None:
    if not value or not value.strip():
        if required:
            raise ValueError("Foto wajib diupload")
        return None

    cleaned = value.strip()
    if cleaned.startswith("/uploads/"):
        return cleaned

    if not cleaned.startswith("data:image/") or ";base64," not in cleaned:
        raise ValueError("Format foto tidak valid")

    if len(cleaned) > MAX_IMAGE_DATA_URL_LENGTH:
        raise ValueError("Foto terlalu besar. Coba ambil foto lebih dekat atau resolusi lebih kecil.")

    return cleaned


def validate_proof_image(proof_image: str | None, *, required: bool = True) -> str | None:
    try:
        return normalize_image_data_url(proof_image, required=required)
    except ValueError as exc:
        detail = str(exc)
        if required and detail == "Foto wajib diupload":
            detail = "Foto bukti wajib diupload"
        raise HTTPException(status_code=400, detail=detail) from exc
