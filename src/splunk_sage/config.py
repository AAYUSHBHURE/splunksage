"""Configuration loaded from environment variables / .env file."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="SPLUNK_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Connection
    host: str = "localhost"
    port: int = 8089
    verify_ssl: bool = True
    search_timeout: int = 60

    # Auth — token is used for port 8089 (direct REST API)
    token: str = ""

    # Auth — username/password is used for port 443 (Splunk Cloud web session)
    username: str = ""
    password: str = ""

    # Defaults
    default_index: str = "main"


settings = Settings()
