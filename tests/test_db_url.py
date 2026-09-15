from app.config import Settings


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


def test_local_url_no_ssl_args():
    s = Settings(database_url="postgresql+asyncpg://sentinel:sentinel@localhost:5432/sentinel")
    assert s.database_connect_args() == {}
