# FaceWatch

**Multi-camera face recognition with a live web dashboard.**

FaceWatch detects and recognises faces from USB cameras, network streams, or video files. It displays live camera feeds and records recognised and unknown face sightings with timestamps.

## Features

- Automatic USB camera detection and support for multiple cameras
- Support for RTSP/HTTP camera streams and video files
- Add people from photos or capture a face from a live camera
- Live dashboard with camera feeds, face labels, activity logs, and statistics
- Export activity logs to CSV
- CPU-based processing; no GPU or database server required
- Optional custom YOLOv8 face detector

## Tech stack

- **Backend:** Python, FastAPI, OpenCV, SQLite
- **Frontend:** React, Vite
- **Face detection:** YuNet by default, optional YOLOv8
- **Face recognition:** SFace
- **Live updates:** WebSocket

## Requirements

- Python 3.9+
- Node.js 18+
- Internet connection on first run to download the face models

## Getting started

### 1. Start the backend

```bash
cd backend
python -m venv venv
```

Activate the virtual environment:

```bash
# Windows
venv\Scripts\activate

# macOS / Linux
source venv/bin/activate
```

Install dependencies and start the API:

```bash
pip install -r requirements.txt
python run.py
```

The backend runs at `http://127.0.0.1:8000`.

### 2. Start the frontend

Open a second terminal:

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173` in your browser.

## How to use

1. Open **People** and add a person's name with clear photos, or capture a face from a camera.
2. Open **Live view** to see camera feeds and recognition results.
3. Use the **Dashboard** and **Activity log** to review sightings.
4. Use **Settings** to manage cameras and recognition/logging options.
5. Export filtered activity logs using **Export CSV**.

For better results, use clear, well-lit photos with the face visible. Multiple photos from different angles can improve matching.

## Project structure

```text
FaceWatch/
├── backend/
│   ├── run.py
│   ├── requirements.txt
│   ├── app/
│   │   ├── main.py
│   │   ├── cameras.py
│   │   ├── face_engine.py
│   │   ├── database.py
│   │   └── config.py
│   ├── models/
│   └── data/        # Created at runtime; contains database and face images
└── frontend/
    ├── package.json
    ├── public/config.js
    └── src/
```

## Configuration and deployment

- The backend listens on `127.0.0.1:8000` by default.
- Use `--host 0.0.0.0` to allow connections from other devices on the network.
- Configure allowed frontend origins with `--cors` or `FACEWATCH_CORS_ORIGINS`.
- Set `--api-key` or `FACEWATCH_API_KEY` before exposing the backend to other devices.
- For hosted deployments, configure the frontend with the backend URL. An HTTPS frontend requires an HTTPS backend.
- USB cameras must be connected to the computer running the backend. Remote servers can only access network cameras they can reach.

API documentation is available at `http://127.0.0.1:8000/docs` while the backend is running.

## Using a custom YOLOv8 model

1. Install Ultralytics in the backend virtual environment:

   ```bash
   pip install ultralytics
   ```

2. Place your model weights at `backend/models/yolov8_face_best.pt`.
3. Restart the backend and select the custom detector in Settings if available.

YOLOv8 is used for face detection; SFace still performs face recognition.

## Privacy and limitations

Face data and snapshots are biometric personal data. Inform people where required, restrict access, and protect the `backend/data/` directory. Use an API key and HTTPS when exposing the backend beyond your own computer.

Face recognition can make mistakes, particularly with poor lighting, unusual angles, masks, or small faces. Do not rely on it as the sole basis for high-impact decisions. The application uses CPU processing and local storage, so performance and scale depend on the computer running it.
