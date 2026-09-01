from app.core.config import settings


def get_upload_url(path: str | None) -> str | None:
    if not path:
        return path

    if path.startswith(("http://", "https://", "data:")):
        return path

    if path.startswith("/uploads/"):
        return f"{settings.backend_base_url.rstrip('/')}{path}"

    return path
