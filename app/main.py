import os
import re
import uuid
import shutil
import sqlite3
from pathlib import Path
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, Request, Form, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from openpyxl import load_workbook

from .db import connect, init_db
from .security import verify_admin, make_code, load_env_file

load_env_file()
BASE_DIR = Path(__file__).resolve().parent.parent
UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", "uploads"))
if not UPLOAD_DIR.is_absolute():
    UPLOAD_DIR = BASE_DIR / UPLOAD_DIR
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="Điểm danh hội nghị")
app.add_middleware(
    SessionMiddleware,
    secret_key=os.getenv("APP_SECRET", "dev-only-change-this-secret"),
    same_site="lax",
    https_only=os.getenv("COOKIE_HTTPS_ONLY", "false").lower() == "true",
)
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "app" / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "app" / "templates"))
init_db()

def is_admin(request: Request) -> bool:
    return request.session.get("role") == "admin"

def participant_id(request: Request):
    if request.session.get("role") == "participant":
        return request.session.get("participant_id")
    return None

def admin_guard(request: Request):
    if not is_admin(request):
        raise HTTPException(status_code=401, detail="Bạn cần đăng nhập admin.")

def normalized(value) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()

def render(request: Request, template: str, context: dict, status_code: int = 200):
    base = {"request": request, "is_admin": is_admin(request)}
    base.update(context)
    return templates.TemplateResponse(request=request, name=template, context=base, status_code=status_code)

@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    if is_admin(request):
        return RedirectResponse("/admin", status_code=303)
    if participant_id(request):
        return RedirectResponse("/documents", status_code=303)
    return RedirectResponse("/login", status_code=303)

@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return render(request, "login.html", {"error": None, "page_title": "Đăng nhập đại biểu"})

@app.post("/login", response_class=HTMLResponse)
def login(request: Request, code: str = Form(...), full_name: str = Form(...)):
    code, full_name = normalized(code).upper(), normalized(full_name)
    with connect() as c:
        person = c.execute(
            "SELECT * FROM participants WHERE upper(code)=? AND lower(full_name)=lower(?)",
            (code, full_name)
        ).fetchone()
    if not person:
        return render(request, "login.html", {
            "error": "Không tìm thấy đại biểu phù hợp. Vui lòng kiểm tra mã đại biểu và họ tên.",
            "page_title": "Đăng nhập đại biểu"
        }, 400)
    request.session.clear()
    request.session["role"] = "participant"
    request.session["participant_id"] = person["id"]
    return RedirectResponse("/documents", status_code=303)

@app.get("/admin/login", response_class=HTMLResponse)
def admin_login_page(request: Request):
    return render(request, "admin_login.html", {"error": None, "page_title": "Đăng nhập quản trị"})

@app.post("/admin/login", response_class=HTMLResponse)
def admin_login(request: Request, username: str = Form(...), password: str = Form(...)):
    if not verify_admin(normalized(username), password):
        return render(request, "admin_login.html", {
            "error": "Tên đăng nhập hoặc mật khẩu không đúng.",
            "page_title": "Đăng nhập quản trị"
        }, 400)
    request.session.clear()
    request.session["role"] = "admin"
    return RedirectResponse("/admin", status_code=303)

@app.post("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=303)

@app.get("/documents", response_class=HTMLResponse)
def documents_page(request: Request):
    pid = participant_id(request)
    if not pid:
        if is_admin(request):
            return RedirectResponse("/admin", status_code=303)
        return RedirectResponse("/login", status_code=303)
    with connect() as c:
        person = c.execute("SELECT * FROM participants WHERE id=?", (pid,)).fetchone()
        docs = c.execute("SELECT * FROM documents ORDER BY uploaded_at DESC, id DESC").fetchall()
    if not person:
        request.session.clear()
        return RedirectResponse("/login", status_code=303)
    return render(request, "participant.html", {
        "page_title": "Văn bản hội nghị", "person": person, "documents": docs
    })

@app.get("/admin", response_class=HTMLResponse)
def admin_page(request: Request, q: str = "", status: str = "all", message: str = "", error: str = ""):
    if not is_admin(request):
        return RedirectResponse("/admin/login", status_code=303)
    clauses, params = [], []
    if q.strip():
        like = f"%{q.strip()}%"
        clauses.append("(full_name LIKE ? OR code LIKE ? OR organization LIKE ? OR role LIKE ?)")
        params.extend([like, like, like, like])
    if status == "present":
        clauses.append("checked_in=1")
    elif status == "absent":
        clauses.append("checked_in=0")
    sql = "SELECT * FROM participants"
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY CASE WHEN role LIKE '%Chủ trì%' THEN 0 ELSE 1 END, full_name COLLATE NOCASE"
    with connect() as c:
        people = c.execute(sql, params).fetchall()
        total = c.execute("SELECT COUNT(*) n FROM participants").fetchone()["n"]
        present = c.execute("SELECT COUNT(*) n FROM participants WHERE checked_in=1").fetchone()["n"]
        docs = c.execute("SELECT * FROM documents ORDER BY uploaded_at DESC, id DESC").fetchall()
    return render(request, "admin.html", {
        "page_title": "Quản trị hội nghị", "people": people, "documents": docs,
        "total": total, "present": present, "absent": total-present,
        "q": q, "status": status, "message": message, "error": error
    })

@app.post("/admin/import-excel")
async def import_excel(request: Request, file: UploadFile = File(...)):
    if not is_admin(request):
        return RedirectResponse("/admin/login", status_code=303)
    if not file.filename or Path(file.filename).suffix.lower() not in {".xlsx", ".xlsm"}:
        return RedirectResponse("/admin?error=" + "Vui%20l%C3%B2ng%20t%E1%BA%A3i%20file%20.xlsx", status_code=303)
    tmp_path = UPLOAD_DIR / f"import_{uuid.uuid4().hex}.xlsx"
    try:
        content = await file.read()
        if len(content) > 10 * 1024 * 1024:
            raise ValueError("File Excel vượt quá giới hạn 10 MB.")
        tmp_path.write_bytes(content)
        wb = load_workbook(tmp_path, read_only=True, data_only=True)
        ws = wb.active
        rows = ws.iter_rows(values_only=True)
        headers = [normalized(v).lower() for v in next(rows, [])]
        aliases = {
            "code": {"mã đại biểu", "ma dai bieu", "mã", "ma", "code", "delegate id", "id"},
            "name": {"họ tên", "ho ten", "họ và tên", "ho va ten", "tên đại biểu", "ten dai bieu", "full name", "name"},
            "role": {"vai trò", "vai tro", "role", "loại đại biểu", "loai dai bieu"},
            "organization": {"đơn vị", "don vi", "cơ quan", "co quan", "organization", "agency"},
            "position": {"chức vụ", "chuc vu", "position", "title"},
        }
        indexes = {}
        for key, options in aliases.items():
            for i, h in enumerate(headers):
                if h in options:
                    indexes[key] = i
                    break
        if "name" not in indexes:
            raise ValueError("Không tìm thấy cột Họ tên. Hãy đặt tiêu đề cột là 'Họ tên'.")
        imported, skipped = 0, 0
        with connect() as c:
            for row in rows:
                def cell(key):
                    i = indexes.get(key)
                    return normalized(row[i]) if i is not None and i < len(row) and row[i] is not None else ""
                name = cell("name")
                if not name:
                    skipped += 1
                    continue
                code = cell("code").upper() or make_code()
                role = cell("role") or "Thành viên"
                org, position = cell("organization"), cell("position")
                try:
                    c.execute("""
                        INSERT INTO participants(code, full_name, role, organization, position)
                        VALUES(?,?,?,?,?)
                        ON CONFLICT(code) DO UPDATE SET
                            full_name=excluded.full_name, role=excluded.role,
                            organization=excluded.organization, position=excluded.position
                    """, (code, name, role, org, position))
                    imported += 1
                except sqlite3.IntegrityError:
                    skipped += 1
        wb.close()
        return RedirectResponse(f"/admin?message=Đã%20nhập%20hoặc%20cập%20nhật%20{imported}%20đại%20biểu%3B%20bỏ%20qua%20{skipped}%20dòng.", status_code=303)
    except Exception as exc:
        msg = str(exc).replace(" ", "%20")
        return RedirectResponse(f"/admin?error={msg}", status_code=303)
    finally:
        try:
            tmp_path.unlink(missing_ok=True)
        except Exception:
            pass

@app.post("/admin/documents")
async def upload_document(request: Request, title: str = Form(...), file: UploadFile = File(...)):
    if not is_admin(request):
        return RedirectResponse("/admin/login", status_code=303)
    if not file.filename or Path(file.filename).suffix.lower() != ".pdf":
        return RedirectResponse("/admin?error=Ch%E1%BB%89%20ch%E1%BA%A5p%20nh%E1%BA%ADn%20file%20PDF", status_code=303)
    content = await file.read()
    if len(content) > 30 * 1024 * 1024:
        return RedirectResponse("/admin?error=File%20PDF%20v%C6%B0%E1%BB%A3t%2030%20MB", status_code=303)
    if not content.startswith(b"%PDF-"):
        return RedirectResponse("/admin?error=File%20kh%C3%B4ng%20ph%E1%BA%A3i%20PDF%20h%E1%BB%A3p%20l%E1%BB%87", status_code=303)
    safe_name = f"{uuid.uuid4().hex}.pdf"
    (UPLOAD_DIR / safe_name).write_bytes(content)
    clean_title = normalized(title) or Path(file.filename).stem
    with connect() as c:
        c.execute("INSERT INTO documents(title, original_name, stored_name) VALUES(?,?,?)",
                  (clean_title, Path(file.filename).name, safe_name))
    return RedirectResponse("/admin?message=Đã%20tải%20lên%20văn%20bản", status_code=303)

@app.post("/admin/attendance/{person_id}")
def toggle_attendance(request: Request, person_id: int, action: str = Form(...)):
    if not is_admin(request):
        return RedirectResponse("/admin/login", status_code=303)
    if action not in {"checkin", "undo"}:
        raise HTTPException(status_code=400, detail="Thao tác không hợp lệ.")
    with connect() as c:
        if action == "checkin":
            c.execute("UPDATE participants SET checked_in=1, checked_in_at=CURRENT_TIMESTAMP WHERE id=?", (person_id,))
        else:
            c.execute("UPDATE participants SET checked_in=0, checked_in_at=NULL WHERE id=?", (person_id,))
    return RedirectResponse("/admin", status_code=303)

@app.post("/admin/documents/{doc_id}/delete")
def delete_document(request: Request, doc_id: int):
    if not is_admin(request):
        return RedirectResponse("/admin/login", status_code=303)
    with connect() as c:
        doc = c.execute("SELECT * FROM documents WHERE id=?", (doc_id,)).fetchone()
        if doc:
            c.execute("DELETE FROM documents WHERE id=?", (doc_id,))
            try:
                (UPLOAD_DIR / doc["stored_name"]).unlink(missing_ok=True)
            except OSError:
                pass
    return RedirectResponse("/admin", status_code=303)

@app.get("/documents/{doc_id}/view")
def view_document(request: Request, doc_id: int):
    if not is_admin(request) and not participant_id(request):
        return RedirectResponse("/login", status_code=303)
    with connect() as c:
        doc = c.execute("SELECT * FROM documents WHERE id=?", (doc_id,)).fetchone()
    if not doc:
        raise HTTPException(status_code=404, detail="Không tìm thấy văn bản.")
    path = UPLOAD_DIR / doc["stored_name"]
    if not path.exists():
        raise HTTPException(status_code=404, detail="Tệp PDF không tồn tại trên máy chủ.")
    return FileResponse(path, media_type="application/pdf", filename=doc["original_name"], content_disposition_type="inline")

@app.get("/health")
def health():
    return {"status": "ok"}
