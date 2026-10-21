import hashlib
import hmac
import os
from pathlib import Path

def load_env_file(path: str = ".env") -> None:
    """Tiny .env loader; existing process environment variables take precedence."""
    p = Path(path)
    if not p.exists():
        return
    for raw in p.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)

load_env_file()

def verify_admin(username: str, password: str) -> bool:
    expected_user = os.getenv("ADMIN_USERNAME", "admin")
    expected_password = os.getenv("ADMIN_PASSWORD", "ChangeMe123!")
    return hmac.compare_digest(username, expected_user) and hmac.compare_digest(password, expected_password)

def make_code() -> str:
    import secrets
    return "DG-" + secrets.token_hex(3).upper()
