from functools import lru_cache
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="GCL_", env_file=str(ROOT / ".env"), extra="ignore")
    data_dir: Path = ROOT / "data"
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    ee_project: str | None = None
    ee_service_account: str | None = None
    ee_private_key_file: str | None = None
    api_token: str | None = None            # if set, state-changing endpoints require "Authorization: Bearer <token>"
    static_dir: Path | None = None          # built frontend to serve from the API process (Docker / single-node)
    log_json: bool = False
    max_upload_mb: int = 5
    rate_limit_per_min: int = 600           # read requests per client per minute (heavy = /6, write = /4); 0 disables
    min_completeness: float = 0.5            # a series with fewer valid months than this fraction is NOT stored

    @property
    def cors_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    d = Path(s.data_dir)
    s.data_dir = (d if d.is_absolute() else ROOT / d).resolve()      # relative paths are anchored to the repo root, not the CWD
    return s
