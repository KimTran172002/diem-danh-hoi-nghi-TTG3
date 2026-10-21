import os
import sqlite3
from pathlib import Path
from contextlib import contextmanager
from .security import load_env_file

load_env_file()
DB_PATH = os.getenv("DATABASE_PATH", "data/attendance.db")
Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)

@contextmanager
def connect():
    conn = sqlite3.connect(DB_PATH, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()

def init_db():
    with connect() as c:
        c.executescript("""
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
        """)
