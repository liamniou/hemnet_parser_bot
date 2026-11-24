import secrets
from functools import lru_cache
from pathlib import Path
from typing import Annotated

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    data_dir: Path = Path("/data")
    public_url: str = "http://localhost:8000"
    secret_key: str = ""
    session_days: int = 30

    telegram_bot_token: str = ""
    telegram_bot_username: str = ""
    telegram_polling: bool = True
    admin_telegram_ids: Annotated[list[int], NoDecode] = []

    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    smtp_security: str = "starttls"  # starttls | ssl | none

    scheduler_enabled: bool = True
    scan_interval_minutes: int = 15
    full_scan_hours: int = 24
    sold_scan_hours: int = 6
    max_pages_per_scan: int = 50
    request_delay_seconds: float = 2.0
    detail_batch_size: int = 20

    archive_images: bool = True
    archive_seed_images: bool = True
    image_max_size: int = 1024
    image_quality: int = 70
    min_free_disk_gb: float = 5.0

    dev_login: bool = False

    @field_validator("admin_telegram_ids", mode="before")
    @classmethod
    def _split_ids(cls, v):
        if isinstance(v, str):
            return [int(x) for x in v.replace(";", ",").split(",") if x.strip()]
        return v

    def ensure_secret_key(self) -> None:
        """Without a strong SECRET_KEY, generate one and persist it in the data dir."""
        if len(self.secret_key) >= 16:
            return
        path = self.data_dir / "secret_key"
        if path.exists():
            self.secret_key = path.read_text().strip()
        else:
            self.secret_key = secrets.token_urlsafe(48)
            path.write_text(self.secret_key)
            path.chmod(0o600)

    @property
    def db_path(self) -> Path:
        return self.data_dir / "hemnet.db"

    @property
    def images_dir(self) -> Path:
        return self.data_dir / "images"

    @property
    def smtp_enabled(self) -> bool:
        return bool(self.smtp_host and self.smtp_from)

    @property
    def telegram_enabled(self) -> bool:
        return bool(self.telegram_bot_token)


@lru_cache
def get_settings() -> Settings:
    return Settings()
