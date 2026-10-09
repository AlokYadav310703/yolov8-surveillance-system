"""Start the FaceWatch API:  python run.py   (API on http://127.0.0.1:8000, docs on /docs)"""
import argparse
import os


def main() -> None:
    parser = argparse.ArgumentParser(description="FaceWatch backend")
    parser.add_argument("--host", default="127.0.0.1", help="use 0.0.0.0 to accept connections from other devices")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--api-key", help="require this key on every request (recommended when hosted)")
    parser.add_argument("--cors", help="comma-separated website addresses allowed to use this API, e.g. https://my-ui.netlify.app")
    args = parser.parse_args()

    # Must be set before the app is imported (config.py reads them).
    if args.api_key:
        os.environ["FACEWATCH_API_KEY"] = args.api_key
    if args.cors:
        os.environ["FACEWATCH_CORS_ORIGINS"] = args.cors

    from app.face_engine import ensure_models
    ensure_models()                                   # downloads the models on the first run

    import uvicorn
    shown = "127.0.0.1" if args.host in ("0.0.0.0", "::") else args.host
    print(f"\nFaceWatch API running at http://{shown}:{args.port}   (API docs: /docs, Ctrl+C to stop)")
    print("Start the web interface from the 'frontend' folder:  npm install && npm run dev\n")
    if os.getenv("FACEWATCH_API_KEY"):
        print("Access key is ON: the web interface will ask for it.\n")
    elif args.host not in ("127.0.0.1", "localhost"):
        print("WARNING: no access key set. Anyone who can reach this address can see the cameras and faces.")
        print("         Start with --api-key YOUR_SECRET to protect it.\n")
    uvicorn.run("app.main:app", host=args.host, port=args.port, log_level="info", access_log=False)


if __name__ == "__main__":
    main()
