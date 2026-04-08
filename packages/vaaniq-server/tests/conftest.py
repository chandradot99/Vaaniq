"""
Test fixtures.

Uses a real PostgreSQL test database (vaaniq_test).
Create it once before running tests locally:
    docker exec vaaniq-postgres-1 psql -U vaaniq -c "CREATE DATABASE vaaniq_test;"

CI creates vaaniq_test automatically in the workflow.
Tables are created once per session and truncated after each test.
"""
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from vaaniq.server.core.database import Base, get_db
from vaaniq.server.main import app

TEST_DATABASE_URL = "postgresql+asyncpg://vaaniq:vaaniq@localhost:5432/vaaniq_test"


@pytest.fixture(scope="session")
async def engine():
    _engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield _engine
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await _engine.dispose()


@pytest.fixture
async def db(engine) -> AsyncSession:
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session


@pytest.fixture(autouse=True)
async def truncate(engine):
    """Truncate all tables after each test using a separate connection."""
    yield
    async with engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            await conn.execute(table.delete())


@pytest.fixture
async def client(db: AsyncSession) -> AsyncClient:
    """HTTP client with the DB dependency overridden to use the test session."""
    async def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


# ── Helpers ───────────────────────────────────────────────────────────────────

@pytest.fixture
async def registered_user(client: AsyncClient) -> dict:
    """Register a user and return the full response payload."""
    response = await client.post("/v1/auth/register", json={
        "email": "user@example.com",
        "name": "Test User",
        "password": "Password1",
        "org_name": "Acme Inc",
    })
    assert response.status_code == 201
    return response.json()


@pytest.fixture
def auth_headers(registered_user: dict) -> dict:
    """Bearer headers for an already-registered user."""
    return {"Authorization": f"Bearer {registered_user['access_token']}"}
