import logging
import os

from dotenv import load_dotenv
load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from backend.db import Base, engine
from backend.models import models  # noqa: F401  (registers models on Base)
from backend.api.routes import router as api_router

app = FastAPI(
    title="AI Operations Automation Agent",
    description="Agentic AI pipeline that classifies incoming requests, checks order/shipment "
                 "status, applies business rules, generates a response, notifies a human channel, "
                 "and measures its own performance.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup():
    Base.metadata.create_all(bind=engine)


app.include_router(api_router, prefix="/api", tags=["ops-agent"])

# Serve the metrics dashboard as static files at /dashboard
dashboard_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "dashboard")
if os.path.isdir(dashboard_dir):
    app.mount("/dashboard", StaticFiles(directory=dashboard_dir, html=True), name="dashboard")


@app.get("/")
def root():
    return {
        "service": "AI Operations Automation Agent",
        "docs": "/docs",
        "dashboard": "/dashboard",
        "submit_a_request": "POST /api/requests {\"text\": \"...\"}",
    }
