from __future__ import annotations

import os
import pathlib
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from src.api.admin import router as admin_router
from src.api.routes import router
from src.api.scraper import router as scraper_router
from src.core import database, ml_model
from src.core.config import get_settings


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    settings = get_settings()
    # When SKIP_STARTUP=1 is set in the environment, skip heavy initialisation
    # (DB pool and ML model) so the app can start quickly for testing.
    skip = os.environ.get("SKIP_STARTUP", "0") == "1"
    if not skip:
        database.init_pool()
        ml_model.load_model()
        print(f"App ready — http://{settings.app_host}:{settings.app_port}")
    else:
        print("SKIP_STARTUP=1 set — skipping DB pool and ML model initialisation")
    yield
    if not skip:
        database.close_pool()


app = FastAPI(
    title="FYP CLIP",
    version="1.0.0",
    lifespan=lifespan,
)

app.mount("/static", StaticFiles(directory="static"), name="static")

_image_root = get_settings().image_root or "."
app.mount("/images", StaticFiles(directory=_image_root), name="images")

_data_dir = "Data"
pathlib.Path(_data_dir).mkdir(exist_ok=True)
app.mount("/data", StaticFiles(directory=_data_dir), name="data")

app.include_router(router)
app.include_router(admin_router)
app.include_router(scraper_router)


@app.get("/", include_in_schema=False)
async def root() -> FileResponse:
    return FileResponse("static/index.html")


@app.get("/admin", include_in_schema=False)
async def admin_page() -> FileResponse:
    return FileResponse("static/admin.html")
