import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.routers import businesses, catalogue, documents, profile

# Importing these registers the task handlers.
from app.services import catalogue_tasks, profile_drafter  # noqa: F401

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

settings = get_settings()
if settings.auth_mode == "dev":
    logging.getLogger(__name__).warning(
        "AUTH_MODE=dev: the API trusts the X-User-Email header. Never deploy this way."
    )

app = FastAPI(title="AI Business OS API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"ok": True}


for module in (businesses, documents, catalogue, profile):
    app.include_router(module.router, prefix="/api")
