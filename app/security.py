import hmac
import os
import secrets
from pathlib import Path


# =========================================================
# ĐỌC FILE .ENV
# =========================================================

def load_env_file(path=".env"):
    """
    Đọc biến môi trường từ file .env.

    Nếu biến đã tồn tại trong môi trường hệ thống,
    giá trị của hệ thống sẽ được ưu tiên.
    """

    env_path = Path(path)

    if not env_path.is_absolute():
        env_path = (
            Path(__file__).resolve().parent.parent / env_path
        )

    if not env_path.is_file():
        return

    try:
        lines = env_path.read_text(
            encoding="utf-8"
        ).splitlines()

    except OSError:
        return

    for raw_line in lines:
        line = raw_line.strip()

        if not line:
            continue

        if line.startswith("#"):
            continue

        if "=" not in line:
            continue

        key, value = line.split("=", 1)

        key = key.strip()
        value = value.strip()

        if value.startswith('"') and value.endswith('"'):
            value = value[1:-1]

        elif value.startswith("'") and value.endswith("'"):
            value = value[1:-1]

        if key:
            os.environ.setdefault(key, value)


# Nạp cấu hình khi module được import.
load_env_file()


# =========================================================
# XÁC THỰC QUẢN TRỊ VIÊN
# =========================================================

def verify_admin(username: str, password: str) -> bool:
    """
    Kiểm tra tài khoản quản trị viên.

    Không sử dụng tài khoản/mật khẩu mặc định.
    Nếu chưa cấu hình thông tin đăng nhập thì từ chối.
    """

    expected_username = os.getenv(
        "ADMIN_USERNAME", ""
    ).strip()

    expected_password = os.getenv(
        "ADMIN_PASSWORD", ""
    )

    if not expected_username or not expected_password:
        return False

    username_match = hmac.compare_digest(
        username.encode("utf-8"),
        expected_username.encode("utf-8")
    )

    password_match = hmac.compare_digest(
        password.encode("utf-8"),
        expected_password.encode("utf-8")
    )

    return username_match and password_match


# =========================================================
# TẠO MÃ ĐẠI BIỂU
# =========================================================

def make_code() -> str:
    """
    Sinh mã đại biểu ngẫu nhiên.

    Ví dụ: DG-A81F29C4

    Database vẫn chịu trách nhiệm kiểm tra mã trùng.
    """

    return "DG-" + secrets.token_hex(4).upper()