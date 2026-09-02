from app.core.upload_url import get_upload_url, resolve_avatar_url


def test_get_upload_url_none():
    assert get_upload_url(None) is None
    assert get_upload_url("") == ""


def test_get_upload_url_absolute_unchanged():
    assert get_upload_url("https://cdn.example.com/a.jpg") == "https://cdn.example.com/a.jpg"
    assert get_upload_url("data:image/png;base64,abc") == "data:image/png;base64,abc"


def test_get_upload_url_relative_uploads(monkeypatch):
    monkeypatch.setattr(
        "app.core.upload_url.settings.backend_base_url",
        "https://family-mission-be.onrender.com",
    )
    assert (
        get_upload_url("/uploads/2_abc.jpg")
        == "https://family-mission-be.onrender.com/uploads/2_abc.jpg"
    )


def test_get_upload_url_other_path_unchanged(monkeypatch):
    monkeypatch.setattr(
        "app.core.upload_url.settings.backend_base_url",
        "https://family-mission-be.onrender.com",
    )
    assert get_upload_url("/other/path.jpg") == "/other/path.jpg"


def test_resolve_avatar_url_data_url():
    assert resolve_avatar_url("data:image/jpeg;base64,abc") == "data:image/jpeg;base64,abc"


def test_resolve_avatar_url_missing_upload(monkeypatch, tmp_path):
    monkeypatch.setattr("app.core.upload_url.settings.upload_dir", str(tmp_path))
    assert resolve_avatar_url("/uploads/missing.jpg") is None


def test_resolve_avatar_url_legacy_upload_always_null():
    assert resolve_avatar_url("/uploads/exists.jpg") is None
    assert (
        resolve_avatar_url("https://family-mission-be.onrender.com/uploads/exists.jpg")
        is None
    )
