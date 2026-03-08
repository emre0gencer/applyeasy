"""FastAPI application — CORS, routers, startup."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent.parent / ".env")  # backend/.env

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.src.api.routes import download, generate, status, upload
from backend.src.storage.database import init_db


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="AI Resume & Cover Letter Tailoring System",
    description="Constrained LLM generation grounded in verified candidate source material.",
    version="1.0.0",
    lifespan=lifespan,
)

# Allow the Vite dev server and any localhost origin
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:3000",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(upload.router, prefix="/api")
app.include_router(generate.router, prefix="/api")
app.include_router(status.router, prefix="/api")
app.include_router(download.router, prefix="/api")


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}
