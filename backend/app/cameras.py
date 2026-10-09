"""
Camera handling. Each camera runs TWO threads so the video never waits for the AI:

  capture thread     reads frames as fast as the camera produces them, keeps only the newest,
                     and JPEG-encodes it for browsers that are watching.
  recognition thread takes the newest frame whenever it is free, finds + tracks + matches faces
                     and writes the log. If it is slow, the video is not affected - only the
                     boxes update a little later.

CameraManager scans for USB cameras every few seconds, so plugging one in just works.
"""
from __future__ import annotations

import logging
import os
import re
import threading
import time
import uuid

import cv2

from . import config
from . import database as db
from .face_engine import crop_face

log = logging.getLogger("facewatch.cameras")

RENDITIONS = {"large": config.STREAM_LARGE, "small": config.STREAM_SMALL}   # name -> (width, fps, quality)


def open_usb(index: int):
    """Try to open a USB camera. Returns an opened capture or None."""
    backend = cv2.CAP_DSHOW if os.name == "nt" else cv2.CAP_ANY
    cap = cv2.VideoCapture(index, backend)
    if not cap.isOpened():
        cap.release()
        return None
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))   # lets cheap cameras do HD at 30 fps
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, config.CAPTURE_WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, config.CAPTURE_HEIGHT)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)                              # always show the newest frame
    ok, _ = cap.read()
    if not ok:
        cap.release()
        return None
    return cap


def iou(a, b) -> float:
    """Overlap of two (x, y, w, h) boxes, 0..1."""
    ax2, ay2, bx2, by2 = a[0] + a[2], a[1] + a[3], b[0] + b[2], b[1] + b[3]
    iw = min(ax2, bx2) - max(a[0], b[0])
    ih = min(ay2, by2) - max(a[1], b[1])
    if iw <= 0 or ih <= 0:
        return 0.0
    inter = iw * ih
    return inter / (a[2] * a[3] + b[2] * b[3] - inter)


class Track:
    """A face followed from one pass to the next, so we only re-run recognition once in a while."""

    def __init__(self, box):
        self.box = box
        self.pid = None
        self.name = None
        self.sim = 0.0
        self.last_embed = 0.0
        self.last_seen = 0.0


class CameraWorker(threading.Thread):
    def __init__(self, mgr: "CameraManager", cam_id: str, name: str, kind: str, source, cap=None, paused: bool = False):
        super().__init__(daemon=True, name=f"cam-{cam_id}")
        self.mgr, self.cam_id, self.name_, self.kind, self.source, self.cap = mgr, cam_id, name, kind, source, cap
        self.paused = paused            # stopped by the user: the camera device is released
        self.stop_evt = threading.Event()
        self.online = False
        self.dead = False
        self.fps = 0.0
        self.faces_now = 0
        # newest raw frame
        self._frame = None
        self._frame_id = 0
        self._frame_lock = threading.Lock()
        # encoded video for viewers: rendition -> (frame number, jpeg bytes)
        self._jpeg = {q: (0, None) for q in RENDITIONS}
        self._jpeg_n = {q: 0 for q in RENDITIONS}
        self._want_until = {q: 0.0 for q in RENDITIONS}
        self._last_enc = {q: 0.0 for q in RENDITIONS}
        # recognition output
        self.frame_size = (0, 0)
        self.tracks: list[Track] = []
        self._faces: list[dict] = []
        self.det_version = 0
        self.last_logged: dict = {}

    # ------------------------------------------------------------ used by the API
    def latest_frame(self):
        with self._frame_lock:
            return None if self._frame is None else self._frame.copy()

    def set_paused(self, paused: bool) -> None:
        self.paused = paused
        self.det_version += 1

    def want(self, quality: str) -> None:
        """A browser is watching: keep producing this video size for the next few seconds."""
        self._want_until[quality] = time.time() + 3

    def get_jpeg(self, quality: str):
        return self._jpeg[quality]

    def detections(self):
        w, h = self.frame_size
        return self.det_version, {"t": "det", "cam": self.cam_id, "name": self.name_, "w": w, "h": h,
                                  "faces": self._faces, "online": self.online, "paused": self.paused, "fps": round(self.fps, 1)}

    # ------------------------------------------------------------ capture thread
    def run(self) -> None:
        threading.Thread(target=self._recognition_loop, daemon=True, name=f"rec-{self.cam_id}").start()
        try:
            while not self.stop_evt.is_set():
                if self.paused:
                    if self.cap is not None or self.online:
                        self._release()                # stopped by the user: free the camera for other apps
                    self.stop_evt.wait(0.2)
                    continue
                if self.cap is None:
                    self.cap = open_usb(self.source) if self.kind == "usb" else self._open_network()
                if self.cap is None:
                    self._set_offline()
                    if self.kind == "usb":
                        break                          # not there any more: the scanner will re-add it
                    self.stop_evt.wait(5)
                    continue
                self._capture_loop()
                self._release()
                if self.paused:
                    continue
                if self.kind == "usb":
                    break                              # unplugged: the scanner will re-add it
                self.stop_evt.wait(3)                  # network stream dropped: retry
        except Exception:
            log.exception("Camera %s crashed", self.cam_id)
        finally:
            self._release()
            self.dead = True

    def _open_network(self):
        cap = cv2.VideoCapture(str(self.source))
        if not cap.isOpened():
            cap.release()
            return None
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        return cap

    def _set_offline(self) -> None:
        self.online = False
        self.faces_now = 0
        self.tracks, self._faces = [], []
        self.fps = 0.0
        self.det_version += 1          # tells watching browsers the camera went offline

    def _release(self) -> None:
        self._set_offline()
        if self.cap is not None:
            self.cap.release()
            self.cap = None

    def _capture_loop(self) -> None:
        cap = self.cap
        is_file = self.kind == "network" and os.path.isfile(str(self.source))
        frame_dt = 1.0 / (cap.get(cv2.CAP_PROP_FPS) or 25) if is_file else 0.0
        fails, frames = 0, 0
        t0 = time.time()
        self.online = True
        self.det_version += 1
        while not self.stop_evt.is_set() and not self.paused:
            t_start = time.time()
            ok, frame = cap.read()
            if not ok:
                fails += 1
                if is_file:
                    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)          # loop video files
                    if fails > 3:
                        return
                    continue
                if fails >= 30:
                    return                                        # camera unplugged / stream lost
                time.sleep(0.05)
                continue
            fails = 0
            with self._frame_lock:
                self._frame = frame
                self._frame_id += 1
            now = time.time()
            self._encode_for_viewers(frame, now)
            frames += 1
            if now - t0 >= 2:
                self.fps, frames, t0 = frames / (now - t0), 0, now
            if is_file:
                time.sleep(max(0.0, frame_dt - (time.time() - t_start)))

    def _encode_for_viewers(self, frame, now: float) -> None:
        H, W = frame.shape[:2]
        for q, (width, fps, quality) in RENDITIONS.items():
            if self._want_until[q] <= now:
                if self._jpeg[q][1] is not None:
                    self._jpeg[q] = (self._jpeg[q][0], None)      # nobody watching: free the memory
                continue
            if now - self._last_enc[q] < 0.7 / fps:               # 0.7 so a 30 fps camera isn't cut to 15
                continue
            k = min(1.0, width / W)
            img = cv2.resize(frame, (int(W * k), int(H * k))) if k < 1 else frame
            ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, quality])
            if ok:
                self._last_enc[q] = now
                self._jpeg_n[q] += 1
                self._jpeg[q] = (self._jpeg_n[q], buf.tobytes())

    # ------------------------------------------------------------ recognition thread
    def _recognition_loop(self) -> None:
        last_id = -1
        while not (self.stop_evt.is_set() or self.dead):
            with self._frame_lock:
                fid, frame = self._frame_id, self._frame
            if frame is None or fid == last_id or not self.online:
                self.stop_evt.wait(0.01)
                continue
            last_id = fid
            t0 = time.time()
            self._process(frame, t0)
            self.stop_evt.wait(max(0.0, config.DETECT_INTERVAL - (time.time() - t0)))

    def _process(self, frame, now: float) -> None:
        try:
            engine, gallery = self.mgr.engine, self.mgr.gallery
            settings = db.get_settings()
            H, W = frame.shape[:2]
            unmatched = list(self.tracks)
            current: list[Track] = []
            for face in sorted(engine.detect(frame), key=lambda f: -f.w * f.h):
                box = (face.x, face.y, face.w, face.h)
                best, best_iou = None, config.TRACK_IOU
                for t in unmatched:
                    v = iou(box, t.box)
                    if v > best_iou:
                        best, best_iou = t, v
                if best is not None:
                    unmatched.remove(best)
                    track = best
                    track.box = box
                else:
                    track = Track(box)
                track.last_seen = now

                age = now - track.last_embed
                if age >= (config.REEMBED_KNOWN if track.name else config.REEMBED_UNKNOWN):
                    emb = engine.embed(frame, face)
                    if emb is not None:
                        track.pid, track.name, track.sim = gallery.match(emb, settings["threshold"])
                        track.last_embed = now
                        self._maybe_log(frame, face, track.pid, track.name, track.sim, now, settings)
                current.append(track)

            self.tracks = current + [t for t in unmatched if now - t.last_seen < config.TRACK_TTL]
            self._faces = [{"x": t.box[0], "y": t.box[1], "w": t.box[2], "h": t.box[3],
                            "name": t.name, "sim": round(t.sim, 3)} for t in current]
            self.frame_size = (W, H)
            self.faces_now = len(current)
            self.det_version += 1
        except Exception:
            log.exception("Processing error on %s", self.cam_id)

    def _maybe_log(self, frame, face, pid, name, sim, now, settings) -> None:
        if pid is None and not settings["log_unknown"]:
            return
        key = pid if pid is not None else "unknown"
        cooldown = settings["cooldown"] if pid is not None else config.UNKNOWN_COOLDOWN
        if now - self.last_logged.get(key, 0.0) < cooldown:
            return
        self.last_logged[key] = now

        snapshot = None
        crop = crop_face(frame, face, 0.3)
        if crop.size:
            ok, buf = cv2.imencode(".jpg", crop, [cv2.IMWRITE_JPEG_QUALITY, 85])
            if ok:
                snapshot = f"{uuid.uuid4().hex}.jpg"
                (config.SNAP_DIR / snapshot).write_bytes(buf.tobytes())
        db.execute(
            "INSERT INTO detections(ts, person_id, person_name, camera_id, camera_name, similarity, snapshot) "
            "VALUES(?,?,?,?,?,?,?)",
            (now, pid, name or "Unknown", self.cam_id, self.name_, sim, snapshot),
        )


class CameraManager:
    def __init__(self, engine, gallery) -> None:
        self.engine, self.gallery = engine, gallery
        self.workers: dict[str, CameraWorker] = {}
        self.lock = threading.RLock()
        self.stop_evt = threading.Event()
        self.scanning = False

    # ------------------------------------------------------------ lifecycle
    def start(self) -> None:
        for row in db.query("SELECT * FROM cameras WHERE kind='network'"):
            self._spawn(row["id"], row["name"], "network", row["source"], paused=not row["enabled"])
        threading.Thread(target=self._scan_loop, daemon=True, name="camera-scanner").start()

    def stop(self) -> None:
        self.stop_evt.set()
        with self.lock:
            workers = list(self.workers.values())
        for w in workers:
            w.stop_evt.set()
        for w in workers:
            w.join(timeout=3)

    def _scan_loop(self) -> None:
        while not self.stop_evt.is_set():
            try:
                self.scan()
            except Exception:
                log.exception("Camera scan failed")
            self.stop_evt.wait(config.SCAN_INTERVAL)

    # ------------------------------------------------------------ discovery
    def scan(self) -> None:
        """Find USB cameras that are not running yet. Safe to call at any time."""
        with self.lock:
            if self.scanning:
                return
            self.scanning = True
            for cid in [c for c, w in self.workers.items() if w.dead]:    # forget unplugged cameras
                del self.workers[cid]
        try:
            for index in range(config.MAX_CAMERA_INDEX):
                cid = f"usb{index}"
                with self.lock:
                    if cid in self.workers or self.stop_evt.is_set():
                        continue
                cap = open_usb(index)
                if cap is None:
                    continue
                row = db.one("SELECT name, enabled FROM cameras WHERE id=?", (cid,))
                if row:
                    name, enabled = row["name"], bool(row["enabled"])
                else:
                    name, enabled = f"Camera {index}", True
                    db.execute("INSERT INTO cameras(id, name, source, kind) VALUES(?,?,?,?)",
                               (cid, name, str(index), "usb"))
                log.info("Found camera %s", cid)
                if not enabled:                      # the user stopped it earlier: keep it stopped
                    cap.release()
                    cap = None
                self._spawn(cid, name, "usb", index, cap, paused=not enabled)
        finally:
            self.scanning = False

    def _spawn(self, cam_id, name, kind, source, cap=None, paused=False) -> None:
        worker = CameraWorker(self, cam_id, name, kind, source, cap, paused)
        with self.lock:
            self.workers[cam_id] = worker
        worker.start()

    # ------------------------------------------------------------ user actions
    def add_network(self, name: str, source: str) -> str:
        cam_id = "net" + uuid.uuid4().hex[:6]
        db.execute("INSERT INTO cameras(id, name, source, kind) VALUES(?,?,?,?)", (cam_id, name, source, "network"))
        self._spawn(cam_id, name, "network", source)
        return cam_id

    def remove(self, cam_id: str) -> bool:
        with self.lock:
            worker = self.workers.get(cam_id)
            if worker is None or worker.kind != "network":
                return False
            del self.workers[cam_id]
        worker.stop_evt.set()
        db.execute("DELETE FROM cameras WHERE id=?", (cam_id,))
        return True

    def set_enabled(self, cam_id: str, enabled: bool) -> bool:
        """Stop (release the device) or start a camera. The choice is remembered across restarts."""
        worker = self.get(cam_id)
        if worker is None:
            return False
        worker.set_paused(not enabled)
        db.execute("UPDATE cameras SET enabled=? WHERE id=?", (1 if enabled else 0, cam_id))
        return True

    def rename(self, cam_id: str, name: str) -> bool:
        worker = self.get(cam_id)
        if worker is None:
            return False
        worker.name_ = name
        worker.det_version += 1
        db.execute("UPDATE cameras SET name=? WHERE id=?", (name, cam_id))
        return True

    def get(self, cam_id: str) -> CameraWorker | None:
        with self.lock:
            return self.workers.get(cam_id)

    def list(self) -> list[dict]:
        with self.lock:
            workers = sorted(self.workers.values(), key=lambda w: w.cam_id)
        out = []
        for w in workers:
            source = f"USB camera {w.source}" if w.kind == "usb" else re.sub(r"://[^/@]+@", "://***@", str(w.source))
            out.append({
                "id": w.cam_id, "name": w.name_, "kind": w.kind, "source": source,
                "online": w.online, "paused": w.paused, "fps": round(w.fps, 1), "faces": w.faces_now,
            })
        return out
