from __future__ import annotations

import os
from functools import lru_cache

from dotenv import load_dotenv

load_dotenv()


class Settings:
    db_name: str
    db_user: str
    db_password: str
    db_host: str
    db_port: str

    model_name: str
    model_path: str

    image_root: str

    hnsw_ef_search: int
    search_limit: int

    app_host: str
    app_port: int

    admin_password: str
    browser_binary: str

    def __init__(self) -> None:
        self.db_name = os.environ["DB_NAME"]
        self.db_user = os.environ["DB_USER"]
        self.db_password = os.environ["DB_PASSWORD"]
        self.db_host = os.environ.get("DB_HOST", "localhost")
        self.db_port = os.environ.get("DB_PORT", "5432")

        self.model_name = os.environ.get("MODEL_NAME", "ViT-B-32")
        self.model_path = os.environ["MODEL_PATH"]

        self.image_root = os.environ.get("IMAGE_ROOT", "")

        self.hnsw_ef_search = int(os.environ.get("HNSW_EF_SEARCH", "40"))
        self.search_limit = int(os.environ.get("SEARCH_LIMIT", "5"))

        self.app_host = os.environ.get("APP_HOST", "0.0.0.0")
        self.app_port = int(os.environ.get("APP_PORT", "8000"))

        self.admin_password = os.environ.get("ADMIN_PASSWORD", "")
        self.browser_binary = os.environ.get("BROWSER_BINARY", "/usr/bin/microsoft-edge")

    @property
    def db_dsn(self) -> dict[str, str]:
        return {
            "dbname": self.db_name,
            "user": self.db_user,
            "password": self.db_password,
            "host": self.db_host,
            "port": self.db_port,
        }


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
