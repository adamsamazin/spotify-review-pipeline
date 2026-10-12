"""Local preview: serves the static dashboard and the API together (production uses Vercel routing).

    .venv/Scripts/python -m uvicorn dashboard.dev_server:app --port 8765
"""
from pathlib import Path

from dotenv import load_dotenv
from fastapi.staticfiles import StaticFiles

load_dotenv(Path(__file__).resolve().parent.parent / ".env")
from dashboard.api.index import app  # noqa: E402  (needs DATABASE_URL loaded first)

app.mount("/", StaticFiles(directory=Path(__file__).parent / "public", html=True), name="static")
