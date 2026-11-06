"""Environment-driven settings and data modes.

Demo, Imported and Live data live in SEPARATE MongoDB databases and are never
mixed. Accounts live in a fourth database. Settings refuse to load if any two
of them share a name.
"""

from enum import Enum
from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class DataMode(str, Enum):
    DEMO = "demo"
    IMPORTED = "imported"
    LIVE = "live"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore", validate_assignment=False)

    mongo_uri: str = "mongodb://localhost:27017"
    mongo_db_demo: str = "marketlens_demo"
    mongo_db_imported: str = "marketlens_imported"
    mongo_db_live: str = "marketlens_live"
    mongo_db_accounts: str = "marketlens_accounts"

    # Live stays off until a provider, credentials and limits are configured.
    live_provider_enabled: bool = False

    cors_origins: str = "http://localhost:5173,http://localhost:8080"
    # Set true whenever the app is served over HTTPS.
    cookie_secure: bool = False
    session_hours: int = 12

    import_max_bytes: int = 10_000_000
    import_max_rows: int = 200_000

    worker_poll_seconds: int = 10
    # Where the demo generator writes its CSV export and separate answer key.
    demo_export_dir: str = "data/demo-export"
    log_level: str = "INFO"

    @model_validator(mode="after")
    def _modes_use_separate_databases(self) -> "Settings":
        names = [self.mongo_db_demo, self.mongo_db_imported, self.mongo_db_live, self.mongo_db_accounts]
        if len(set(names)) != len(names):
            raise ValueError(
                "Demo, Imported, Live and Accounts must use separate databases; " f"got {names}"
            )
        return self

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    def database_for(self, mode: DataMode) -> str:
        return {
            DataMode.DEMO: self.mongo_db_demo,
            DataMode.IMPORTED: self.mongo_db_imported,
            DataMode.LIVE: self.mongo_db_live,
        }[mode]

    def mode_unavailable_reason(self, mode: DataMode) -> str | None:
        """None when the mode can be used; otherwise a plain-language reason."""
        if mode is DataMode.LIVE and not self.live_provider_enabled:
            return "Live data is off: no live provider is configured."
        return None


@lru_cache
def get_settings() -> Settings:
    return Settings()
