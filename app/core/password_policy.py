import re

SPECIAL_CHARS = re.compile(r"[!@#$%^&*(),.?\":{}|<>_\-\+=\[\]\\;/'`~]")


def validate_password_strength(password: str) -> None:
    """Raise ValueError with Indonesian message if password fails policy."""
    if len(password) < 8:
        raise ValueError("Password minimal 8 karakter")
    if not re.search(r"[A-Z]", password):
        raise ValueError("Password harus mengandung minimal 1 huruf besar")
    if not re.search(r"[a-z]", password):
        raise ValueError("Password harus mengandung minimal 1 huruf kecil")
    if not re.search(r"\d", password):
        raise ValueError("Password harus mengandung minimal 1 angka")
    if not SPECIAL_CHARS.search(password):
        raise ValueError("Password harus mengandung minimal 1 karakter khusus (!@#$%^&* dll.)")
