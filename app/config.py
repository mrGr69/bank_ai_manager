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
        url = self.database_url
        if url.startswith("postgres://"):
            url = "postgresql://" + url[len("postgres://") :]
        if url.startswith("postgresql://") and "+asyncpg" not in url:
            url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
        if url.startswith("postgresql+psycopg2://"):
            url = url.replace("postgresql+psycopg2://", "postgresql+asyncpg://", 1)
        if any(h in url for h in ("rlwy.net", "railway.app", "proxy.rlwy")) and "ssl" not in url:
            url += ("&" if "?" in url else "?") + "ssl=require"
        return url


settings = Settings()
