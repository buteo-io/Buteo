"""Application settings, loaded from environment + ``.env``.

Every runtime configuration value (secrets, hosts, cookie flags, CORS list)
flows through :class:`Settings`. The object is cached; mutate via env vars,
not attribute assignment. The module refuses to load if ``JWT_SECRET`` is
missing or matches any known insecure default.

Used by: API, ingest (Codec 8 + OsmAnd), CLI, Alembic, tracker_core.
"""

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_FORBIDDEN_SECRETS = {
    "",
    "change-me",
    "changeme",
    "dev-only-change-me",
    "dev-only-change-me-dev-only-change-me",
    "change-me-please-32+chars-random",
    "secret",
}


class Settings(BaseSettings):
    """Typed view over the environment. Instantiated once per process."""

    app_name: str = "gps-tracker"
    log_level: str = "INFO"

    data_dir: str | None = None

    database_type: str = "sqlite"  # 'sqlite' or 'postgres'

    postgres_user: str = "tracker"
    postgres_password: str = "change-me"
    postgres_db: str = "tracker"
    postgres_db_host: str = "localhost"
    postgres_db_port: str = "55432"

    ingest_host: str = "0.0.0.0"
    ingest_codec8_port: int = 5027
    ingest_osmand_port: int = 8766

    api_host: str = "0.0.0.0"
    api_port: int = 8765
    api_upstream: str = "api:8765"

    cors_origins: str = "http://localhost:5173"

    docs_enabled: bool = True

    jwt_secret: str = ""
    jwt_expire_min: int = 14400
    jwt_alg: str = "HS256"
    jwt_issuer: str = "gps-tracker"
    jwt_audience: str = "gps-tracker-web"
    share_token_pepper: str = ""

    auth_cookie_name: str = "tracker_session"
    auth_cookie_secure: bool = True
    dev_insecure_cookies: bool = False

    max_image_size_mb: int = 20
    max_video_size_mb: int = 500
    max_audio_size_mb: int = 50

    model_config = SettingsConfigDict(
        env_file=(".env", "../.env", "../../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @model_validator(mode="after")
    def _validate_settings(self) -> "Settings":
        db_type = self.database_type.strip().lower()
        if db_type not in ("sqlite", "postgres"):
            raise ValueError("database_type must be either 'sqlite' or 'postgres'")

        if db_type == "sqlite":
            if not self.data_dir:
                raise ValueError("data_dir must be specified when using SQLite database type")
        else:
            self._check_postgres_vars()
        return self

    def _check_postgres_vars(self) -> None:
        missing = []
        if not self.postgres_user:
            missing.append("postgres_user")
        if not self.postgres_password:
            missing.append("postgres_password")
        if not self.postgres_db_host:
            missing.append("postgres_db_host")
        if not self.postgres_db_port:
            missing.append("postgres_db_port")
        if not self.postgres_db:
            missing.append("postgres_db")
        if missing:
            raise ValueError(f"Missing required PostgreSQL variables: {', '.join(missing)}")

    @property
    def identity_database_url(self) -> str:
        db_type = self.database_type.strip().lower()
        if db_type == "sqlite":
            return f"sqlite+aiosqlite:///{self.data_dir}/identity.db"
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_db_host}:{self.postgres_db_port}/tracker_identity"
        )

    @field_validator("jwt_secret")
    @classmethod
    def _check_jwt_secret(cls, v: str) -> str:
        norm = v.strip().lower()
        if norm in _FORBIDDEN_SECRETS:
            raise ValueError(
                "JWT_SECRET is missing or set to a known-default value. "
                "Set JWT_SECRET in your environment to a random 32+ char string "
                "(e.g. `openssl rand -hex 32`).",
            )
        if len(v) < 32:
            raise ValueError("JWT_SECRET must be at least 32 characters. Generate one with `openssl rand -hex 32`.")
        return v

    @property
    def cors_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


AppConfig = Settings()
