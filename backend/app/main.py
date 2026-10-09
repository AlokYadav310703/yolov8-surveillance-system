"""FaceWatch - FastAPI backend (API + WebSocket only). Run with:  python run.py"""
from __future__ import annotations

import asyncio
import csv
import io
import secrets
import time
from contextlib import asynccontextmanager
from datetime import datetime
from typing import List, Optional

import cv2
import numpy as np
from fastapi import FastAPI, File, Form, HTTPException, UploadFile, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import config
from . import database as db
from .cameras import CameraManager
from .face_engine import FaceEngine, Gallery, crop_face

engine: FaceEngine
gallery = Gallery()
manager: CameraManager


@asynccontextmanager
async def lifespan(app: FastAPI):
    global engine, manager
    db.init()
    engine = FaceEngine()
    gallery.reload()
    manager = CameraManager(engine, gallery)
    manager.start()
    yield
    manager.stop()


app = FastAPI(title="FaceWatch API", lifespan=lifespan)
app.mount("/snapshots", StaticFiles(directory=config.SNAP_DIR), name="snapshots")

OPEN_PATHS = {"/", "/api/health", "/docs", "/openapi.json", "/redoc"}


def _key_ok(supplied: str) -> bool:
    return secrets.compare_digest(supplied.encode(), config.API_KEY.encode())


@app.middleware("http")
async def require_key(request, call_next):
    """If FACEWATCH_API_KEY is set, every request must carry it (X-API-Key header or ?key=)."""
    if config.API_KEY and request.method != "OPTIONS" and request.url.path not in OPEN_PATHS:
        supplied = request.headers.get("x-api-key") or request.query_params.get("key") or ""
        if not _key_ok(supplied):
            return JSONResponse({"detail": "Invalid or missing access key."}, status_code=401)
    return await call_next(request)


# Added last so it wraps everything above (even error responses get CORS headers).
app.add_middleware(CORSMiddleware, allow_origins=config.CORS_ORIGINS, allow_methods=["*"], allow_headers=["*"])


@app.get("/", include_in_schema=False)
def root():
    return {"name": "FaceWatch API", "docs": "/docs", "health": "/api/health"}


@app.get("/api/health")
def health():
    return {"status": "ok", "auth_required": bool(config.API_KEY), "detector": engine.name}


# =============================================================== cameras
class NewCamera(BaseModel):
    name: str
    source: str


class Rename(BaseModel):
    name: str


def _cam(cam_id: str):
    worker = manager.get(cam_id)
    if worker is None:
        raise HTTPException(404, "Camera not found")
    return worker


@app.get("/api/cameras")
def list_cameras():
    return {"cameras": manager.list(), "scanning": manager.scanning}


@app.post("/api/cameras/rescan")
async def rescan_cameras():
    await run_in_threadpool(manager.scan)
    return {"cameras": manager.list()}


@app.post("/api/cameras")
def add_camera(cam: NewCamera):
    name, source = cam.name.strip(), cam.source.strip()
    if not name or not source:
        raise HTTPException(400, "Enter a name and a stream address (or a video file path).")
    return {"id": manager.add_network(name[:60], source)}


@app.put("/api/cameras/{cam_id}")
def rename_camera(cam_id: str, body: Rename):
    name = body.name.strip()[:60]
    if not name:
        raise HTTPException(400, "Name cannot be empty.")
    if not manager.rename(cam_id, name):
        raise HTTPException(404, "Camera not found")
    return {"ok": True}


@app.post("/api/cameras/{cam_id}/stop")
def stop_camera(cam_id: str):
    if not manager.set_enabled(cam_id, False):
        raise HTTPException(404, "Camera not found")
    return {"ok": True}


@app.post("/api/cameras/{cam_id}/start")
def start_camera(cam_id: str):
    if not manager.set_enabled(cam_id, True):
        raise HTTPException(404, "Camera not found")
    return {"ok": True}


@app.delete("/api/cameras/{cam_id}")
def remove_camera(cam_id: str):
    if not manager.remove(cam_id):
        raise HTTPException(400, "Only network cameras can be removed. USB cameras disappear when unplugged.")
    return {"ok": True}


@app.websocket("/ws")
async def live_socket(ws: WebSocket):
    """
    One WebSocket carries everything live, for all cameras.
      browser -> server : {"sub": {"usb0": "large", "net1a2b3c": "small"}}   (what I want to watch)
      server -> browser : text   {"t":"det","cam":...,"w":..,"h":..,"faces":[{x,y,w,h,name,sim}],"online":..,"fps":..}
                          binary [1 byte id length][camera id][JPEG bytes]
    Only the newest frame is ever sent, so a slow connection skips frames instead of lagging behind.
    """
    if config.API_KEY and not _key_ok(ws.query_params.get("key", "")):
        await ws.close(code=4401)
        return
    await ws.accept()
    subs: dict[str, str] = {}
    sent_frame: dict = {}
    sent_det: dict = {}

    async def reader():
        try:
            while True:
                msg = await ws.receive_json()
                if isinstance(msg, dict) and isinstance(msg.get("sub"), dict):
                    subs.clear()
                    subs.update({str(k): v for k, v in msg["sub"].items() if v in ("small", "large")})
        except Exception:
            pass

    task = asyncio.create_task(reader())
    try:
        while not task.done():
            for cam_id, quality in list(subs.items()):
                worker = manager.get(cam_id)
                if worker is None:
                    continue
                worker.want(quality)
                frame_no, jpg = worker.get_jpeg(quality)
                if jpg and sent_frame.get((cam_id, quality)) != frame_no:
                    sent_frame[(cam_id, quality)] = frame_no
                    cid = cam_id.encode()
                    await ws.send_bytes(bytes([len(cid)]) + cid + jpg)
                version, det = worker.detections()
                if sent_det.get(cam_id) != version:
                    sent_det[cam_id] = version
                    await ws.send_json(det)
            await asyncio.sleep(0.01)
    except Exception:
        pass
    finally:
        task.cancel()


# =============================================================== people
def _save_jpeg(path, img) -> None:
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 90])
    if ok:
        path.write_bytes(buf.tobytes())


def _enroll(name: str, images: list) -> dict:
    """Detect the largest face in each image, store its embedding. Blocking - run in a thread."""
    if not name or len(name) > 60:
        raise HTTPException(400, "Enter a name (1-60 characters).")
    if name.lower() == "unknown":
        raise HTTPException(400, "\"Unknown\" is reserved. Please choose another name.")

    found = []
    for img in images:
        H, W = img.shape[:2]
        if max(H, W) > 1600:
            k = 1600 / max(H, W)
            img = cv2.resize(img, (int(W * k), int(H * k)))
        faces = engine.detect(img, min_px=30)
        if not faces:
            continue
        face = max(faces, key=lambda f: f.w * f.h)
        emb = engine.embed(img, face)
        if emb is not None:
            found.append((emb, crop_face(img, face, 0.4, square=True)))
    if not found:
        raise HTTPException(400, "No face found. Use a clear, well-lit photo where the face is visible.")

    row = db.one("SELECT id FROM people WHERE name = ? COLLATE NOCASE", (name,))
    if row:
        pid = row["id"]
    else:
        pid = db.execute("INSERT INTO people(name, created_at) VALUES(?, ?)", (name, time.time()))
    thumb = config.FACES_DIR / f"{pid}.jpg"
    if not thumb.exists():
        _save_jpeg(thumb, cv2.resize(found[0][1], (200, 200)))
    for emb, _ in found:
        db.execute("INSERT INTO embeddings(person_id, vec) VALUES(?, ?)", (pid, emb.astype(np.float32).tobytes()))
    gallery.reload()
    return {"id": pid, "name": name, "added": len(found), "skipped": len(images) - len(found)}


@app.get("/api/people")
def list_people():
    return db.query(
        "SELECT p.id, p.name, p.created_at, "
        "(SELECT COUNT(*) FROM embeddings e WHERE e.person_id = p.id) AS photos, "
        "(SELECT MAX(ts) FROM detections d WHERE d.person_id = p.id) AS last_seen, "
        "(SELECT camera_name FROM detections d WHERE d.person_id = p.id ORDER BY ts DESC LIMIT 1) AS last_camera "
        "FROM people p ORDER BY p.name COLLATE NOCASE"
    )


@app.post("/api/people")
async def add_person(name: str = Form(...), files: List[UploadFile] = File(...)):
    images = []
    for f in files:
        img = cv2.imdecode(np.frombuffer(await f.read(), np.uint8), cv2.IMREAD_COLOR)
        if img is not None:
            images.append(img)
    if not images:
        raise HTTPException(400, "Could not read the image(s). Use JPG or PNG files.")
    return await run_in_threadpool(_enroll, name.strip(), images)


class FromCamera(BaseModel):
    name: str
    camera_id: str


@app.post("/api/people/from-camera")
async def add_person_from_camera(body: FromCamera):
    frame = _cam(body.camera_id).latest_frame()
    if frame is None:
        raise HTTPException(400, "That camera has no video right now.")
    return await run_in_threadpool(_enroll, body.name.strip(), [frame])


@app.get("/api/people/{pid}/photo")
def person_photo(pid: int):
    path = config.FACES_DIR / f"{pid}.jpg"
    if not path.exists():
        raise HTTPException(404)
    return FileResponse(path, headers={"Cache-Control": "max-age=3600"})


@app.delete("/api/people/{pid}")
def delete_person(pid: int):
    if not db.one("SELECT id FROM people WHERE id=?", (pid,)):
        raise HTTPException(404, "Person not found")
    db.execute("DELETE FROM people WHERE id=?", (pid,))       # embeddings are removed by the foreign key
    (config.FACES_DIR / f"{pid}.jpg").unlink(missing_ok=True)
    gallery.reload()
    return {"ok": True}


# =============================================================== logs
def _where(person: Optional[str], camera: Optional[str], start: Optional[float], end: Optional[float]):
    where, params = [], []
    if person:
        where.append("person_name = ? COLLATE NOCASE")
        params.append(person)
    if camera:
        where.append("camera_id = ?")
        params.append(camera)
    if start:
        where.append("ts >= ?")
        params.append(start)
    if end:
        where.append("ts < ?")
        params.append(end)
    return (" WHERE " + " AND ".join(where)) if where else "", tuple(params)


@app.get("/api/logs")
def get_logs(limit: int = 50, offset: int = 0, person: Optional[str] = None, camera: Optional[str] = None,
             start: Optional[float] = None, end: Optional[float] = None):
    clause, params = _where(person, camera, start, end)
    total = db.one(f"SELECT COUNT(*) AS n FROM detections{clause}", params)["n"]
    items = db.query(f"SELECT * FROM detections{clause} ORDER BY ts DESC LIMIT ? OFFSET ?",
                     params + (min(max(limit, 1), 500), max(offset, 0)))
    return {"total": total, "items": items}


@app.get("/api/logs/export.csv")
def export_logs(person: Optional[str] = None, camera: Optional[str] = None,
                start: Optional[float] = None, end: Optional[float] = None):
    clause, params = _where(person, camera, start, end)
    rows = db.query(f"SELECT * FROM detections{clause} ORDER BY ts DESC", params)
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["time", "person", "camera", "similarity"])
    for r in rows:
        writer.writerow([datetime.fromtimestamp(r["ts"]).strftime("%Y-%m-%d %H:%M:%S"), r["person_name"],
                         r["camera_name"], "" if r["similarity"] is None else round(r["similarity"], 3)])
    return Response(buf.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": "attachment; filename=facewatch-log.csv"})


@app.delete("/api/logs")
def clear_logs():
    db.execute("DELETE FROM detections")
    for f in config.SNAP_DIR.glob("*.jpg"):
        f.unlink(missing_ok=True)
    return {"ok": True}


# =============================================================== dashboard + settings
@app.get("/api/stats")
def stats():
    now = time.time()
    midnight = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
    cams = manager.list()

    hourly_start = now - 24 * 3600
    buckets = [{"hour": time.localtime(hourly_start + i * 3600).tm_hour, "known": 0, "unknown": 0} for i in range(24)]
    for r in db.query("SELECT ts, person_id FROM detections WHERE ts >= ?", (hourly_start,)):
        b = buckets[min(23, int((r["ts"] - hourly_start) // 3600))]
        b["known" if r["person_id"] is not None else "unknown"] += 1

    def count(extra: str) -> int:
        return db.one(f"SELECT COUNT(*) AS n FROM detections WHERE ts >= ? {extra}", (midnight,))["n"]

    return {
        "cameras_total": len(cams),
        "cameras_online": sum(1 for c in cams if c["online"]),
        "people": db.one("SELECT COUNT(*) AS n FROM people")["n"],
        "known_today": count("AND person_id IS NOT NULL"),
        "unknown_today": count("AND person_id IS NULL"),
        "total_logs": db.one("SELECT COUNT(*) AS n FROM detections")["n"],
        "hourly": buckets,
        "by_camera": db.query("SELECT camera_name AS name, COUNT(*) AS n FROM detections WHERE ts >= ? "
                              "GROUP BY camera_id ORDER BY n DESC LIMIT 8", (midnight,)),
        "top_people": db.query("SELECT person_name AS name, COUNT(*) AS n FROM detections WHERE ts >= ? "
                               "AND person_id IS NOT NULL GROUP BY person_id ORDER BY n DESC LIMIT 5", (midnight,)),
        "recent": db.query("SELECT * FROM detections ORDER BY ts DESC LIMIT 8"),
    }


class SettingsBody(BaseModel):
    threshold: Optional[float] = None
    cooldown: Optional[int] = None
    log_unknown: Optional[bool] = None


@app.get("/api/settings")
def get_settings():
    return {**db.get_settings(), "detector": engine.name, "recognizer": "SFace"}


@app.put("/api/settings")
def put_settings(body: SettingsBody):
    return db.update_settings(body.model_dump(exclude_none=True))
