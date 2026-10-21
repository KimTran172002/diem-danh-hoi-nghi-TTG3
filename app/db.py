import os
import sqlite3
from pathlib import Path
from contextlib import contextmanager

from .security import load_env_file


# =========================================================
# CẤU HÌNH ĐƯỜNG DẪN
# =========================================================

BASE_DIR = Path(__file__).resolve().parent.parent

load_env_file(BASE_DIR / ".env")

DEFAULT_DB_PATH = BASE_DIR / "data" / "attendance.db"

DB_PATH = Path(
    os.getenv("DATABASE_PATH", str(DEFAULT_DB_PATH))
).expanduser()

if not DB_PATH.is_absolute():
    DB_PATH = (BASE_DIR / DB_PATH).resolve()

DB_PATH.parent.mkdir(parents=True, exist_ok=True)


# =========================================================
# KẾT NỐI DATABASE
# =========================================================

@contextmanager
def connect():
    """
    Mở kết nối SQLite.
    Tự commit khi thành công và rollback nếu xảy ra lỗi.
    """

    conn = sqlite3.connect(
        str(DB_PATH),
        timeout=30
    )

    conn.row_factory = sqlite3.Row

    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 30000")

    try:
        yield conn
        conn.commit()

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()


# =========================================================
# KHỞI TẠO DATABASE
# =========================================================

def init_db():
    """
    Tạo bảng nếu chưa tồn tại.
    Không xóa dữ liệu hiện có.
    """

    with connect() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS participants (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT NOT NULL UNIQUE,
                full_name TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'Thành viên',
                organization TEXT NOT NULL DEFAULT '',
                position TEXT NOT NULL DEFAULT '',
                checked_in INTEGER NOT NULL DEFAULT 0,
                checked_in_at TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS documents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                original_name TEXT NOT NULL,
                stored_name TEXT NOT NULL UNIQUE,
                uploaded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE INDEX IF NOT EXISTS idx_participants_name
                ON participants(full_name);

            CREATE INDEX IF NOT EXISTS idx_participants_checked_in
                ON participants(checked_in);

            CREATE INDEX IF NOT EXISTS idx_documents_uploaded_at
                ON documents(uploaded_at);
        """)