from app.config import Settings, pick_database_url


def test_internal_railway_disables_ssl():
    s = Settings(
        database_url="postgresql://postgres:pass@postgres.railway.internal:5432/railway?sslmode=require"
    )
    assert "sslmode" not in s.async_database_url()
    assert s.database_connect_args() == {"ssl": False}


def test_public_proxy_enables_ssl():
    s = Settings(database_url="postgresql://postgres:pass@switchyard.proxy.rlwy.net:1234/railway")
    args = s.database_connect_args()
    assert "ssl" in args
    assert args["ssl"] is not False


def test_local_url_disables_ssl():
    s = Settings(database_url="postgresql+asyncpg://sentinel:sentinel@localhost:5432/sentinel")
    assert s.database_connect_args() == {"ssl": False}


def test_pick_skips_localhost_when_private_url_exists(monkeypatch):
    monkeypatch.setenv("RAILWAY_ENVIRONMENT", "production")
    monkeypatch.setenv(
        "DATABASE_URL", "postgresql://sentinel:sentinel@localhost:5432/sentinel"
    )
    monkeypatch.setenv(
        "DATABASE_PRIVATE_URL",
        "postgresql://postgres:pass@postgres.railway.internal:5432/railway",
    )
    url, source = pick_database_url("postgresql://sentinel:sentinel@localhost:5432/sentinel")
    assert source == "DATABASE_PRIVATE_URL"
    assert "railway.internal" in url
