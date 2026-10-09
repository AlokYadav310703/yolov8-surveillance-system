"""
Face detection + recognition.

  Detection   : YuNet (OpenCV, default)  -or-  your fine-tuned YOLOv8 face model (models/yolov8_face_best.pt)
  Recognition : SFace (OpenCV) -> 128-number embedding per face, compared with cosine similarity

Only `opencv-python-headless` is needed; `ultralytics` is optional (YOLO detector).

Quick self-test:  python -m app.face_engine some_photo.jpg
"""
from __future__ import annotations

import logging
import threading
import urllib.request
from dataclasses import dataclass

import cv2
import numpy as np

from . import config
from . import database as db

log = logging.getLogger("facewatch.engine")


@dataclass
class Face:
    x: int
    y: int
    w: int
    h: int
    score: float
    row: np.ndarray | None = None      # YuNet row (box + 5 landmarks + score) when available

    def scaled(self, k: float) -> "Face":
        row = None
        if self.row is not None:
            row = self.row.copy()
            row[:14] *= k
        return Face(int(self.x * k), int(self.y * k), int(self.w * k), int(self.h * k), self.score, row)

    def clip(self, width: int, height: int) -> None:
        x1, y1 = max(0, self.x), max(0, self.y)
        x2, y2 = min(width, self.x + self.w), min(height, self.y + self.h)
        self.x, self.y, self.w, self.h = x1, y1, max(0, x2 - x1), max(0, y2 - y1)


def crop_face(img: np.ndarray, face: Face, margin: float = 0.25, square: bool = False) -> np.ndarray:
    """Crop a face with some margin around it (used for snapshots and thumbnails)."""
    H, W = img.shape[:2]
    if square:
        side = int(max(face.w, face.h) * (1 + 2 * margin))
        cx, cy = face.x + face.w // 2, face.y + face.h // 2
        x1, y1, x2, y2 = cx - side // 2, cy - side // 2, cx + side // 2, cy + side // 2
    else:
        mx, my = int(face.w * margin), int(face.h * margin)
        x1, y1, x2, y2 = face.x - mx, face.y - my, face.x + face.w + mx, face.y + face.h + my
    return img[max(0, y1):min(H, y2), max(0, x1):min(W, x2)]


def _ensure_model(path, url) -> None:
    if path.exists() and path.stat().st_size > 50_000:
        return
    print(f"Downloading {path.name} (first run only)...", flush=True)
    tmp = path.with_suffix(".part")
    try:
        urllib.request.urlretrieve(url, tmp)
        if tmp.stat().st_size < 50_000:
            raise RuntimeError("downloaded file is too small")
        tmp.replace(path)
    except Exception as e:
        tmp.unlink(missing_ok=True)
        raise RuntimeError(
            f"Could not download {path.name}: {e}\n"
            f"Download it manually from:\n  {url}\nand put it in the folder: {path.parent}"
        ) from e


def ensure_models() -> None:
    _ensure_model(config.YUNET_PATH, config.YUNET_URL)
    _ensure_model(config.SFACE_PATH, config.SFACE_URL)


class FaceEngine:
    def __init__(self) -> None:
        ensure_models()
        self.lock = threading.RLock()      # OpenCV's detector keeps state, so share it safely
        self.yunet = cv2.FaceDetectorYN.create(str(config.YUNET_PATH), "", (320, 320), 0.8, 0.3, 5000)
        self.sface = cv2.FaceRecognizerSF.create(str(config.SFACE_PATH), "")
        self.yolo = None
        if config.YOLO_WEIGHTS.exists():
            try:
                from ultralytics import YOLO
                self.yolo = YOLO(str(config.YOLO_WEIGHTS))
                log.info("Using custom YOLOv8 face detector: %s", config.YOLO_WEIGHTS.name)
            except Exception as e:
                log.warning("Could not load YOLO weights (%s) - falling back to YuNet", e)
        self.name = "YOLOv8 (custom)" if self.yolo else "YuNet"

    # ---------------------------------------------------------------- detection
    def detect(self, img: np.ndarray, min_px: int | None = None) -> list[Face]:
        """Find faces. Returns boxes in the coordinates of the ORIGINAL image."""
        min_px = config.MIN_FACE_PX if min_px is None else min_px
        H, W = img.shape[:2]
        k = min(1.0, config.DETECT_MAX_SIDE / max(H, W))
        small = cv2.resize(img, (int(W * k), int(H * k))) if k < 1 else img
        with self.lock:
            faces = self._detect_yolo(small) if self.yolo else self._detect_yunet(small)
        out = []
        for f in faces:
            f = f.scaled(1 / k) if k < 1 else f
            f.clip(W, H)
            if min(f.w, f.h) >= min_px:
                out.append(f)
        return out

    def _detect_yunet(self, img: np.ndarray) -> list[Face]:
        self.yunet.setInputSize((img.shape[1], img.shape[0]))
        _, rows = self.yunet.detect(img)
        if rows is None:
            return []
        return [Face(int(r[0]), int(r[1]), int(r[2]), int(r[3]), float(r[14]), r.copy()) for r in rows]

    def _detect_yolo(self, img: np.ndarray) -> list[Face]:
        res = self.yolo.predict(img, conf=config.YOLO_CONF, imgsz=config.YOLO_IMGSZ, verbose=False)[0]
        out = []
        for b in res.boxes:
            x1, y1, x2, y2 = b.xyxy[0].tolist()
            out.append(Face(int(x1), int(y1), int(x2 - x1), int(y2 - y1), float(b.conf[0])))
        return out

    # ---------------------------------------------------------------- recognition
    def _landmarks_for_box(self, img: np.ndarray, face: Face) -> np.ndarray | None:
        """YOLO gives a box only. Run YuNet inside it to get the 5 landmarks used for alignment."""
        H, W = img.shape[:2]
        m = int(0.3 * max(face.w, face.h))
        x0, y0 = max(0, face.x - m), max(0, face.y - m)
        crop = img[y0:min(H, face.y + face.h + m), x0:min(W, face.x + face.w + m)]
        if crop.size == 0:
            return None
        k = max(1.0, 160 / max(crop.shape[:2]))          # enlarge very small crops
        if k > 1:
            crop = cv2.resize(crop, None, fx=k, fy=k)
        self.yunet.setInputSize((crop.shape[1], crop.shape[0]))
        _, rows = self.yunet.detect(crop)
        if rows is None:
            return None
        r = max(rows, key=lambda r: r[2] * r[3]).copy()
        r[:14] /= k
        r[0:14:2] += x0
        r[1:14:2] += y0
        return r

    def embed(self, img: np.ndarray, face: Face) -> np.ndarray | None:
        """Return a unit-length 128-d embedding for one face, or None."""
        with self.lock:
            row = face.row if face.row is not None else self._landmarks_for_box(img, face)
            if row is not None:
                aligned = self.sface.alignCrop(img, np.asarray(row, dtype=np.float32))
            else:
                crop = crop_face(img, face, 0.1)
                if crop.size == 0:
                    return None
                aligned = cv2.resize(crop, (112, 112))
            feat = self.sface.feature(aligned)
        v = np.asarray(feat, dtype=np.float32).flatten()
        n = float(np.linalg.norm(v))
        return v / n if n > 0 else None


class Gallery:
    """All enrolled embeddings in memory for fast matching."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.ids: list[int] = []
        self.names: list[str] = []
        self.mat = np.zeros((0, 128), dtype=np.float32)

    def reload(self) -> None:
        rows = db.query("SELECT e.person_id, p.name, e.vec FROM embeddings e "
                        "JOIN people p ON p.id = e.person_id")
        ids = [r["person_id"] for r in rows]
        names = [r["name"] for r in rows]
        mat = (np.stack([np.frombuffer(r["vec"], dtype=np.float32) for r in rows])
               if rows else np.zeros((0, 128), dtype=np.float32))
        with self.lock:
            self.ids, self.names, self.mat = ids, names, mat

    def match(self, emb: np.ndarray, threshold: float):
        """-> (person_id, name, similarity). person_id/name are None if nobody is similar enough."""
        with self.lock:
            ids, names, mat = self.ids, self.names, self.mat
        if len(ids) == 0:
            return None, None, 0.0
        sims = mat @ emb
        i = int(np.argmax(sims))
        sim = float(sims[i])
        return (ids[i], names[i], sim) if sim >= threshold else (None, None, sim)


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        sys.exit("usage: python -m app.face_engine photo.jpg")
    image = cv2.imread(sys.argv[1])
    if image is None:
        sys.exit("could not read image")
    engine = FaceEngine()
    found = engine.detect(image, min_px=20)
    print(f"detector: {engine.name} | faces found: {len(found)}")
    for f in found:
        e = engine.embed(image, f)
        print(f"  box=({f.x},{f.y},{f.w},{f.h}) score={f.score:.2f} embedding={None if e is None else e.shape}")
