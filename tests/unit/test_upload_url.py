from app.core.upload_url import get_upload_url


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
