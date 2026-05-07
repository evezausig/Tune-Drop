"""
Simple username/password auth with salted SHA-256 hashing.
"""
import hashlib
import secrets
import db


def _hash(password, salt=None):
    if salt is None:
        salt = secrets.token_hex(16)
    digest = hashlib.sha256(f"{salt}{password}".encode()).hexdigest()
    return f"{salt}:{digest}"


def _verify(password, stored):
    salt, _ = stored.split(":", 1)
    return _hash(password, salt) == stored


def register(username, password):
    """Returns (success: bool, message: str)."""
    username = username.strip()
    if len(username) < 3:
        return False, "Username must be at least 3 characters."
    if len(password) < 6:
        return False, "Password must be at least 6 characters."
    ok = db.create_user(username, _hash(password))
    if ok:
        return True, "Account created!"
    return False, "Username already taken."


def login(username, password):
    """Returns user dict on success, None on failure."""
    user = db.get_user(username.strip())
    if user and _verify(password, user["password_hash"]):
        return user
    return None
