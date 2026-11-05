"""User accounts and login for the customer portal and the admin panel.

Accounts live in data/users.json, created on first run with the admin and some demo customers.
Passwords are stored only as salted PBKDF2 hashes, never as plain text.
"""

import hashlib
import hmac
import json
import re
import secrets
from datetime import datetime
from pathlib import Path

from agents.model_client import _get_secret

ROOT = Path(__file__).resolve().parent
USERS_FILE = ROOT / "data" / "users.json"

DEFAULT_PASSWORD = "Welcome@123"  # every new customer starts with this and can change it in My Account
ADMIN_USERNAME = "admin1"
ITERATIONS = 200_000

# Demo customers; their usernames match the customers in data/orders.json.
DEMO_CUSTOMERS = [
    ("priya", "Priya Sharma"),
    ("arjun", "Arjun Kumar"),
    ("meena", "Meena Iyer"),
    ("karthik", "Karthik Raj"),
    ("rahul", "Rahul Verma"),
    ("anita", "Anita Desai"),
    ("deepa", "Deepa Nair"),
    ("vikram", "Vikram Singh"),
    ("anu", "Anu Thomas"),
    ("ravi", "Ravi Teja"),
]


def _hash(password: str, salt: str | None = None) -> str:
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), ITERATIONS).hex()
    return f"pbkdf2_sha256${ITERATIONS}${salt}${digest}"


def _verify(password: str, stored: str) -> bool:
    try:
        _, iterations, salt, digest = stored.split("$")
        check = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), int(iterations)).hex()
    except ValueError:
        return False
    return hmac.compare_digest(check, digest)


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def _save(users: dict) -> None:
    USERS_FILE.parent.mkdir(parents=True, exist_ok=True)
    USERS_FILE.write_text(json.dumps(users, indent=2), encoding="utf-8")


def _load() -> dict:
    if USERS_FILE.exists():
        return json.loads(USERS_FILE.read_text(encoding="utf-8"))
    # First run: the admin (password from ADMIN_PASSWORD if set, else the default) plus demo customers.
    admin_password = _get_secret("ADMIN_PASSWORD") or "Admin@123"
    users = {ADMIN_USERNAME: {"name": "Support Admin", "role": "admin", "email": "", "password": _hash(admin_password), "created": _now()}}
    for username, name in DEMO_CUSTOMERS:
        users[username] = {"name": name, "role": "customer", "email": "", "password": _hash(DEFAULT_PASSWORD), "created": _now()}
    _save(users)
    return users


def _public(username: str, record: dict) -> dict:
    return {"username": username, **{k: v for k, v in record.items() if k != "password"}}


def authenticate(username: str, password: str) -> dict | None:
    """Return the user (without the password hash) if the login is correct."""
    record = _load().get(username.strip().lower())
    if record and _verify(password, record["password"]):
        return _public(username.strip().lower(), record)
    return None


def list_users() -> list[dict]:
    return [_public(u, r) for u, r in sorted(_load().items())]


def create_user(username: str, name: str, role: str = "customer", email: str = "") -> dict:
    """Create an account with the default password. Raises ValueError for a bad or taken username."""
    username = username.strip().lower()
    if not re.fullmatch(r"[a-z0-9_.]{3,30}", username):
        raise ValueError("Username must be 3 to 30 characters: letters, numbers, dot or underscore.")
    users = _load()
    if username in users:
        raise ValueError(f"The username '{username}' is already taken.")
    users[username] = {
        "name": name.strip() or username,
        "role": "admin" if role == "admin" else "customer",
        "email": email.strip(),
        "password": _hash(DEFAULT_PASSWORD),
        "created": _now(),
    }
    _save(users)
    return _public(username, users[username])


def reset_password(username: str) -> None:
    users = _load()
    users[username]["password"] = _hash(DEFAULT_PASSWORD)
    _save(users)


def change_password(username: str, old: str, new: str) -> str:
    """Change a password; returns an error message, or an empty string when it worked."""
    users = _load()
    if not _verify(old, users[username]["password"]):
        return "Your current password is not correct."
    if len(new) < 8 or not re.search(r"\d", new) or not re.search(r"[A-Za-z]", new):
        return "The new password needs at least 8 characters, with letters and a number."
    users[username]["password"] = _hash(new)
    _save(users)
    return ""
