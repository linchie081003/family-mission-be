from pathlib import Path
from urllib.parse import urlparse

from app.core.config import settings


def get_upload_url(path: str | None) -> str | None:
    if not path:
        return path

    if path.startswith(("http://", "https://", "data:")):
        return path

    if path.startswith("/uploads/"):
        return f"{settings.backend_base_url.rstrip('/')}{path}"

    return path


def _local_upload_path(path: str) -> Path | None:
    """Map /uploads/... or https://host/uploads/... to a path under upload_dir."""
    path_part = path
    if path.startswith(("http://", "https://")):
        path_part = urlparse(path).path

    if not path_part.startswith("/uploads/"):
        return None

    filename = path_part.removeprefix("/uploads/").lstrip("/")
    if not filename or ".." in filename.replace("\\", "/"):
        return None

    return Path(settings.upload_dir) / filename


def resolve_avatar_url(path: str | None) -> str | None:
    """Return avatar URL for API responses.

    Avatars are stored as base64 data URLs in the database (Render-safe).
    Legacy /uploads/ file paths are ignored — those files do not survive redeploys.
    """
    if not path or not path.strip():
        return None

    p = path.strip()
    if p.startswith("data:"):
        return p

    if _local_upload_path(p) is not None:
        return None

    if p.startswith(("http://", "https://")):
        return p

    return get_upload_url(p)
