import asyncio
import os
import shutil
import sqlite3
import time
import uuid
from collections import deque
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, UploadFile, WebSocket
from fastapi.responses import FileResponse, HTMLResponse, Response, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.requests import Request

from pypdf import PdfReader, PdfWriter


load_dotenv()
ADMIN_PASSPHRASE = os.getenv("ADMIN_PASSPHRASE")

# Load or generate admin path
ADMIN_PATH_FILE = Path(".admin_path")
if ADMIN_PATH_FILE.exists():
    ADMIN_PATH = ADMIN_PATH_FILE.read_text().strip()
else:
    ADMIN_PATH = None

print(f"Admin passphrase loaded. Admin path: {ADMIN_PATH or 'Not set yet'}")

UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)

DB_PATH = Path("jobs.db")
MAX_QUEUE = 6
MAX_PASSWORD_LENGTH = 128
DELETE_AFTER_SECONDS = 15 * 60

app = FastAPI(title="DocUnlock")
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

JOB_FIELDS = [
    "id",
    "status",
    "job_dir",
    "input_path",
    "output_path",
    "output_filename",
    "filename",
    "password",
    "created_at",
    "finished_at",
    "error",
    "queue_position",
    "deleted",
    "deleted_at",
]


def get_db_connection():
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_db_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                job_dir TEXT,
                input_path TEXT,
                output_path TEXT,
                output_filename TEXT,
                filename TEXT,
                password TEXT,
                created_at REAL,
                finished_at REAL,
                error TEXT,
                queue_position INTEGER,
                deleted INTEGER DEFAULT 0,
                deleted_at REAL
            )
            """
        )
        conn.execute("UPDATE jobs SET status = 'queued' WHERE status = 'processing'")
        conn.commit()


def row_to_job(row):
    job = dict(row)
    for key in ("job_dir", "input_path", "output_path"):
        if job.get(key) is not None:
            job[key] = Path(job[key])
    job["deleted"] = bool(job.get("deleted", 0))
    return job


def save_job(job):
    values = [
        str(job["id"]),
        job["status"],
        str(job["job_dir"]) if job.get("job_dir") is not None else None,
        str(job["input_path"]) if job.get("input_path") is not None else None,
        str(job["output_path"]) if job.get("output_path") is not None else None,
        job.get("output_filename"),
        job.get("filename"),
        job.get("password"),
        job.get("created_at"),
        job.get("finished_at"),
        job.get("error"),
        job.get("queue_position"),
        int(job.get("deleted", False)),
        job.get("deleted_at"),
    ]
    with get_db_connection() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO jobs (id, status, job_dir, input_path, output_path, output_filename, filename, password, created_at, finished_at, error, queue_position, deleted, deleted_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            values,
        )
        conn.commit()


def load_jobs_from_db():
    global jobs, queue
    jobs = {}
    queue = deque()
    with get_db_connection() as conn:
        rows = conn.execute("SELECT * FROM jobs ORDER BY created_at ASC").fetchall()
    for row in rows:
        job = row_to_job(row)
        jobs[job["id"]] = job
        if job["status"] == "queued":
            queue.append(job["id"])


jobs: dict = {}
queue: deque = deque()
processing_lock = asyncio.Lock()
is_processing = False

connected_clients: set[WebSocket] = set()


async def broadcast_jobs():
    job_list = [
        {
            "id": job_id,
            "status": job_data["status"],
            "created_at": job_data.get("created_at", ""),
            "filename": job_data.get("filename", ""),
            "deleted": job_data.get("deleted", False),
        }
        for job_id, job_data in jobs.items()
    ]
    for client in connected_clients.copy():
        try:
            await client.send_json(job_list)
        except:
            connected_clients.discard(client)


@app.websocket("/ws/admin")
async def admin_websocket(websocket: WebSocket):
    await websocket.accept()
    connected_clients.add(websocket)
    # Send initial jobs
    await broadcast_jobs()
    try:
        while True:
            await websocket.receive_text()
    except:
        connected_clients.discard(websocket)


def is_valid_pdf(file_bytes: bytes) -> bool:
    return file_bytes[:4] == b"%PDF"


def remove_password(input_path: Path, password: str, output_path: Path) -> bool:
    reader = PdfReader(str(input_path))
    if reader.is_encrypted:
        result = reader.decrypt(password)
        if result == 0:
            return False
    writer = PdfWriter()
    for page in reader.pages:
        writer.add_page(page)
    with open(output_path, "wb") as f:
        writer.write(f)
    return True


async def process_queue():
    global is_processing
    while True:
        async with processing_lock:
            if not queue:
                is_processing = False
                return
            job_id = queue.popleft()

        job = jobs.get(job_id)
        if not job:
            continue

        jobs[job_id]["status"] = "processing"
        save_job(jobs[job_id])
        await broadcast_jobs()

        try:
            loop = asyncio.get_event_loop()
            success = await loop.run_in_executor(
                None,
                remove_password,
                job["input_path"],
                job["password"],
                job["output_path"],
            )
            if success:
                jobs[job_id]["status"] = "done"
            else:
                jobs[job_id]["status"] = "error"
                jobs[job_id]["error"] = "Wrong password or could not decrypt."
        except Exception as e:
            jobs[job_id]["status"] = "error"
            jobs[job_id]["error"] = str(e)

        jobs[job_id]["finished_at"] = time.time()
        save_job(jobs[job_id])
        await broadcast_jobs()

    is_processing = False


async def cleanup_old_jobs():
    while True:
        await asyncio.sleep(60)
        now = time.time()
        changed = False
        for job in jobs.values():
            if job.get("deleted"):
                continue
            finished_at = job.get("finished_at")
            created_at = job.get("created_at", now)
            ref_time = finished_at if finished_at else created_at
            if now - ref_time > DELETE_AFTER_SECONDS:
                job_dir = job.get("job_dir")
                if job_dir and Path(job_dir).exists():
                    try:
                        shutil.rmtree(job_dir)
                    except Exception:
                        pass
                else:
                    for p in [job.get("input_path"), job.get("output_path")]:
                        if p and Path(p).exists():
                            try:
                                os.remove(p)
                            except Exception:
                                pass
                job["deleted"] = True
                job["deleted_at"] = now
                save_job(job)
                changed = True
        if changed:
            await broadcast_jobs()


@app.on_event("startup")
async def startup():
    global is_processing
    init_db()
    load_jobs_from_db()
    if queue and not is_processing:
        is_processing = True
        asyncio.create_task(process_queue())
    asyncio.create_task(cleanup_old_jobs())


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    queue_full = len(queue) >= MAX_QUEUE
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "queue_full": queue_full, "max_queue": MAX_QUEUE},
    )


@app.get("/robots.txt", response_class=Response)
async def robots_txt():
    return Response("User-agent: *\nDisallow: /admin*\n", media_type="text/plain")


@app.get("/admin-auth", response_class=HTMLResponse)
async def admin_auth(request: Request):
    return templates.TemplateResponse("admin_auth.html", {"request": request})


@app.post("/admin-auth")
async def admin_auth_post(request: Request, passphrase: str = Form(...)):
    global ADMIN_PATH
    if passphrase == ADMIN_PASSPHRASE:
        ADMIN_PATH = f"/admin-{uuid.uuid4().hex[:8]}"
        ADMIN_PATH_FILE.write_text(ADMIN_PATH)
        print(f"New admin path generated: {ADMIN_PATH}")
        response = RedirectResponse(url=ADMIN_PATH, status_code=303)
        response.set_cookie(
            key="admin_auth", value="true", httponly=True, max_age=3600
        )  # 1 hour
        return response
    else:
        return templates.TemplateResponse(
            "admin_auth.html", {"request": request, "error": "Invalid passphrase"}
        )


@app.get("/admin-{admin_token}", response_class=HTMLResponse)
async def admin(request: Request, admin_token: str):
    if ADMIN_PATH is None or f"/admin-{admin_token}" != ADMIN_PATH:
        return RedirectResponse(url="/admin-auth", status_code=303)
    if request.cookies.get("admin_auth") != "true":
        return RedirectResponse(url="/admin-auth", status_code=303)
    return templates.TemplateResponse("admin.html", {"request": request})


@app.post("/upload")
async def upload(file: UploadFile = File(...), password: str = Form(...)):
    global is_processing

    if len(queue) >= MAX_QUEUE:
        raise HTTPException(
            status_code=503, detail="Queue is full. Please try again later."
        )

    contents = await file.read()

    if not is_valid_pdf(contents):
        raise HTTPException(
            status_code=400,
            detail="File does not appear to be a valid PDF (checked by header).",
        )

    if len(contents) > 50 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File too large. Max 50MB.")

    if len(password.strip()) == 0:
        raise HTTPException(status_code=400, detail="Password is required.")
    if len(password) > MAX_PASSWORD_LENGTH:
        raise HTTPException(
            status_code=400,
            detail=f"Password must be {MAX_PASSWORD_LENGTH} characters or fewer.",
        )

    job_id = str(uuid.uuid4())
    job_dir = UPLOAD_DIR / job_id
    job_dir.mkdir()

    original_name = Path(file.filename).stem if file.filename else "document"
    input_path = job_dir / "locked.pdf"
    output_path = job_dir / f"{original_name}_unlocked.pdf"
    output_filename = output_path.name

    with open(input_path, "wb") as f:
        f.write(contents)

    jobs[job_id] = {
        "id": job_id,
        "status": "queued",
        "job_dir": job_dir,
        "input_path": input_path,
        "output_path": output_path,
        "output_filename": output_filename,
        "filename": file.filename or "document.pdf",
        "password": password,
        "created_at": time.time(),
        "finished_at": None,
        "error": None,
        "queue_position": len(queue) + 1,
        "deleted": False,
        "deleted_at": None,
    }
    save_job(jobs[job_id])

    queue.append(job_id)
    await broadcast_jobs()

    if not is_processing:
        is_processing = True
        asyncio.create_task(process_queue())

    return {"job_id": job_id}


@app.get("/status/{job_id}")
async def status(job_id: str):
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")

    queue_pos = None
    if job["status"] == "queued":
        try:
            queue_pos = list(queue).index(job_id) + 1
        except ValueError:
            queue_pos = 1

    return {
        "status": job["status"],
        "queue_position": queue_pos,
        "error": job.get("error"),
        "output_filename": job.get("output_filename"),
    }


@app.get("/download/{job_id}")
async def download(job_id: str):
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found or already deleted.")
    if job["status"] != "done":
        raise HTTPException(status_code=400, detail="Job not complete.")
    output_path = job["output_path"]
    if not Path(output_path).exists():
        raise HTTPException(
            status_code=410, detail="File has been deleted from server."
        )
    return FileResponse(
        path=str(output_path),
        filename=job["output_filename"],
        media_type="application/pdf",
    )


@app.get("/queue-status")
async def queue_status():
    return {
        "queue_length": len(queue),
        "max_queue": MAX_QUEUE,
        "is_full": len(queue) >= MAX_QUEUE,
    }


@app.get("/job/{job_id}", response_class=HTMLResponse)
async def job_page(request: Request, job_id: str):
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")
    if job["status"] in ("done", "error"):
        return RedirectResponse(url="/", status_code=303)
    return templates.TemplateResponse(
        "job.html", {"request": request, "job_id": job_id}
    )


@app.get("/sw.js")
async def sw():
    return Response(content="", media_type="application/javascript")
