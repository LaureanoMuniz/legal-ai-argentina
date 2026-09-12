from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0 Safari/537.36"
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="LEGAL_AI_", env_file=".env", extra="ignore")

    data_dir: Path = Path("data")
    infoleg_user_agent: str = DEFAULT_USER_AGENT
    infoleg_min_interval_seconds: float = 0.5
    infoleg_timeout_seconds: float = 60.0


@lru_cache
def get_settings() -> Settings:
    return Settings()
