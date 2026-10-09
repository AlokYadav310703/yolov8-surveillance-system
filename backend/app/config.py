"""Central configuration. Edit values here, or override a few with environment variables."""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.getenv("FACEWATCH_DATA_DIR", BASE_DIR / "data"))
SNAP_DIR = DATA_DIR / "snapshots"      # detection snapshots
FACES_DIR = DATA_DIR / "faces"         # enrolled-person thumbnails
MODELS_DIR = Path(os.getenv("FACEWATCH_MODELS_DIR", BASE_DIR / "models"))
DB_PATH = DATA_DIR / "facewatch.db"

for _d in (DATA_DIR, SNAP_DIR, FACES_DIR, MODELS_DIR):
    _d.mkdir(parents=True, exist_ok=True)

# --- Models (downloaded automatically on first run, ~40 MB) -------------------
_ZOO = "https://github.com/opencv/opencv_zoo/raw/main/models"
YUNET_PATH = MODELS_DIR / "face_detection_yunet_2023mar.onnx"
YUNET_URL = f"{_ZOO}/face_detection_yunet/face_detection_yunet_2023mar.onnx"
SFACE_PATH = MODELS_DIR / "face_recognition_sface_2021dec.onnx"
SFACE_URL = f"{_ZOO}/face_recognition_sface/face_recognition_sface_2021dec.onnx"

# Optional: your fine-tuned YOLOv8 face detector. If this file exists (and `ultralytics`
# is installed) it replaces YuNet for face detection. Recognition still uses SFace.
YOLO_WEIGHTS = MODELS_DIR / "yolov8_face_best.pt"
YOLO_CONF = float(os.getenv("FACEWATCH_YOLO_CONF", "0.4"))
YOLO_IMGSZ = int(os.getenv("FACEWATCH_YOLO_IMGSZ", "640"))   # use the size you trained with

# --- Cameras -------------------------------------------------------------------
MAX_CAMERA_INDEX = 10        # probe USB camera indexes 0..9
SCAN_INTERVAL = 10           # seconds between automatic scans for newly plugged cameras
CAPTURE_WIDTH = 1280         # requested from USB cameras (they use the nearest supported size)
CAPTURE_HEIGHT = 720

# --- Processing (runs in its own thread, never slows the video down) -----------
DETECT_MAX_SIDE = 960        # frames are shrunk to this size for detection (speed)
DETECT_INTERVAL = 0.1        # minimum seconds between face-finding passes per camera (0.1 = 10 per second)
REEMBED_KNOWN = 1.0          # a tracked, already-recognised face is re-checked this often (seconds)
REEMBED_UNKNOWN = 0.5        # a tracked, unrecognised face is re-checked this often (seconds)
TRACK_IOU = 0.3              # how much a box must overlap the previous one to count as the same face
TRACK_TTL = 0.6              # keep a lost face's identity this long (seconds)
MIN_FACE_PX = 40             # ignore faces smaller than this many pixels (too small to recognise)
UNKNOWN_COOLDOWN = 30        # seconds between "Unknown" log entries per camera

# --- Live video sent to the browser: (width px, frames per second, JPEG quality) --
STREAM_LARGE = (960, 25, 72)     # Live view page
STREAM_SMALL = (480, 10, 65)     # Dashboard thumbnails

# --- Hosting -------------------------------------------------------------------
API_KEY = os.getenv("FACEWATCH_API_KEY", "")      # if set, every request needs this key
CORS_ORIGINS = [o.strip() for o in os.getenv(
    "FACEWATCH_CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173,http://localhost:4173"
).split(",") if o.strip()]                        # websites allowed to call this API ("*" = any)

# Defaults for settings that can be changed in the UI
DEFAULT_SETTINGS = {
    "threshold": 0.363,      # cosine similarity needed to accept a match (SFace's recommended value)
    "cooldown": 10,          # seconds before the same person is logged again on the same camera
    "log_unknown": True,     # also log faces that match nobody
}
