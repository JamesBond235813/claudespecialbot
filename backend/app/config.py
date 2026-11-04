from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


ROOT_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ROOT_DIR / ".env",
        env_file_encoding="utf-8",
        env_ignore_empty=True,
        extra="ignore",
    )

    app_name: str = "Digital Delivery Bot"
    app_env: str = "development"
    app_host: str = "127.0.0.1"
    app_port: int = 8001
    database_url: str = "mysql+asyncmy://root@127.0.0.1:3306/digital_delivery_bot?charset=utf8mb4"

    telegram_bot_token: str = ""
    telegram_bot_username: str = "ClaudeSpecialbot"
    telegram_admin_chat_id: int | None = None
    admin_api_key: str = Field(default="", min_length=0)

    frontend_origins: str = "http://127.0.0.1:5174,http://localhost:5174"
    business_timezone: str = "Africa/Accra"
    delivery_hour: int = Field(default=10, ge=0, le=23)
    support_handle: str = "@ClaudeSpecialbot"
    terms_version: str = "2026-11-02"
    usdt_network: str = ""
    usdt_receiving_address: str = ""
    payment_public_base_url: str = ""

    bot_mode: str = "polling"
    webhook_base_url: str = ""
    webhook_secret: str = ""

    @property
    def cors_origins(self) -> list[str]:
        return [item.strip() for item in self.frontend_origins.split(",") if item.strip()]

    @property
    def bot_enabled(self) -> bool:
        return bool(self.telegram_bot_token)


@lru_cache
def get_settings() -> Settings:
    return Settings()

