import os

# Must be set before OpenCV is imported anywhere.
os.environ.setdefault("OPENCV_LOG_LEVEL", "SILENT")                        # hide camera-probing noise
os.environ.setdefault("OPENCV_VIDEOIO_PRIORITY_OBSENSOR", "0")             # skip depth-camera probing
os.environ.setdefault("OPENCV_FFMPEG_CAPTURE_OPTIONS", "rtsp_transport;tcp")   # more reliable IP cameras
