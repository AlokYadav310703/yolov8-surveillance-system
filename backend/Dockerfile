# FaceWatch backend. Build:  docker build -t facewatch-api .
# Run (Linux, USB camera):   docker run -p 8000:8000 -v facewatch:/data --device /dev/video0 \
#                              -e FACEWATCH_API_KEY=secret -e FACEWATCH_CORS_ORIGINS=https://your-ui.example.com facewatch-api
# Network (RTSP) cameras work on any OS; USB passthrough only works with Linux hosts.
FROM python:3.11-slim
RUN apt-get update && apt-get install -y --no-install-recommends libglib2.0-0 && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
ENV FACEWATCH_DATA_DIR=/data FACEWATCH_MODELS_DIR=/data/models
VOLUME /data
EXPOSE 8000
CMD ["python", "run.py", "--host", "0.0.0.0"]
