import os
from urllib.parse import quote_plus

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine.url import make_url

_RAILWAY_DB_KEYS = (
    "DATABASE_PRIVATE_URL",
    "DATABASE_URL",
    "POSTGRES_URL",
    "DATABASE_PUBLIC_URL",
)


def on_railway() -> bool:
    return bool(
        os.getenv("RAILWAY_ENVIRONMENT")
        or os.getenv("RAILWAY_SERVICE_ID")
        or os.getenv("RAILWAY_PROJECT_ID")
    )


def _host(url: str) -> str:
    try:
        return (make_url(url).host or "").lower()
    except Exception:
        return ""


def _is_local_host(host: str) -> bool:
    return host in {"localhost", "127.0.0.1", "::1"}


def db_env_debug() -> str:
    parts: list[str] = []
    for key in _RAILWAY_DB_KEYS:
        raw = os.getenv(key)
        if not raw:
            parts.append(f"{key}=missing")
        else:
            parts.append(f"{key}={_host(raw) or 'unparseable'}")
    pghost = os.getenv("PGHOST")
    parts.append(f"PGHOST={pghost or 'missing'}")
    parts.append(f"RAILWAY={on_railway()}")
    return ", ".join(parts)


def pick_database_url(explicit: str) -> tuple[str, str]:
    """Prefer Railway private Postgres. Ignore localhost when running on Railway."""
    candidates: list[tuple[str, str]] = []
    for key in _RAILWAY_DB_KEYS:
        raw = os.getenv(key)
        if raw:
            candidates.append((key, raw))
    candidates.append(("explicit", explicit))
    pghost = os.getenv("PGHOST")
    if pghost:
        user = os.getenv("PGUSER") or "postgres"
        password = os.getenv("PGPASSWORD") or ""
        port = os.getenv("PGPORT") or "5432"
        name = os.getenv("PGDATABASE") or "railway"
        built = f"postgresql://{quote_plus(user)}:{quote_plus(password)}@{pghost}:{port}/{name}"
        candidates.append(("PGHOST", built))

    railway = on_railway()
    seen: set[str] = set()
    for source, url in candidates:
        if url in seen:
            continue
        seen.add(url)
        if railway and _is_local_host(_host(url)):
            continue
        return url, source
    return explicit, "fallback-local"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    telegram_bot_token: str = ""
    telegram_user_id: int | None = None

    monobank_token: str = ""

    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-4o-mini"

    database_url: str = "postgresql+asyncpg://sentinel:sentinel@localhost:5432/sentinel"
    public_url: str = ""
    tz: str = "Europe/Kyiv"
    db_source: str = "default"

    @model_validator(mode="after")
    def resolve_database(self):
        url, source = pick_database_url(self.database_url)
        self.database_url = url
        self.db_source = source
        return self

    def async_database_url(self) -> str:
        url = self.database_url.strip()
        if url.startswith("postgres://"):
            url = "postgresql://" + url[len("postgres://") :]
        if url.startswith("postgresql://") and "+asyncpg" not in url:
            url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
        if url.startswith("postgresql+psycopg2://"):
            url = url.replace("postgresql+psycopg2://", "postgresql+asyncpg://", 1)

        parsed = make_url(url)
        query = dict(parsed.query)
        for key in list(query):
            if key.lower() in {"ssl", "sslmode"}:
                query.pop(key)
        parsed = parsed.set(query=query)
        return parsed.render_as_string(hide_password=False)

    def database_connect_args(self) -> dict:
        """Private Railway Postgres has no TLS. Public proxy requires it."""
        host = _host(self.async_database_url())
        if _is_local_host(host) or host.endswith(".railway.internal"):
            return {"ssl": False}
        if host.endswith(".rlwy.net") or host.endswith(".railway.app"):
            import ssl

            ctx = ssl.create_default_context()
            return {"ssl": ctx}
        return {}

    def database_host_for_log(self) -> str:
        parsed = make_url(self.async_database_url())
        return f"{parsed.host}:{parsed.port}/{parsed.database} via {self.db_source}"


settings = Settings()
