from sqlalchemy.engine.url import make_url
from pydantic_settings import BaseSettings, SettingsConfigDict


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
        host = (make_url(self.async_database_url()).host or "").lower()
        if host.endswith(".railway.internal") or host.endswith(".railway.internal."):
            return {"ssl": False}
        if host.endswith(".rlwy.net") or host.endswith(".railway.app"):
            import ssl

            ctx = ssl.create_default_context()
            return {"ssl": ctx}
        return {}

    def database_host_for_log(self) -> str:
        parsed = make_url(self.async_database_url())
        return f"{parsed.host}:{parsed.port}/{parsed.database}"


settings = Settings()
