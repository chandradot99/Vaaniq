"""Singleton AsyncPostgresSaver — shared across all chat sessions.

Uses psycopg (not asyncpg) as required by langgraph-checkpoint-postgres.
The singleton is initialised once during server startup via setup_checkpointer()
and reused for every graph invocation.

Thread-ID format: "{org_id}:{session_id}" — org-prefixed for multi-tenant
isolation so one org can never accidentally access another org's state.
"""
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg_pool import AsyncConnectionPool
from naaviq.server.core.config import settings

_checkpointer: AsyncPostgresSaver | None = None


def get_checkpointer() -> AsyncPostgresSaver:
    """Return the initialised singleton. Raises if called before setup."""
    if _checkpointer is None:
        raise RuntimeError(
            "Checkpointer not initialised. "
            "Ensure setup_checkpointer() is awaited in the FastAPI lifespan."
        )
    return _checkpointer


async def setup_checkpointer() -> None:
    """Create the AsyncPostgresSaver pool and run schema migrations.

    Must be called once at application startup (FastAPI lifespan).
    AsyncPostgresSaver uses psycopg, which expects a plain postgresql:// URL
    (not postgresql+asyncpg://).

    AsyncPostgresSaver.from_conn_string() is an async context manager, not a
    coroutine — it cannot be awaited directly. Instead we create an
    AsyncConnectionPool explicitly and pass it to the constructor.
    """
    global _checkpointer
    # Strip SQLAlchemy dialect suffix — psycopg uses the base driver URL
    conn_str = settings.database_url.replace("postgresql+asyncpg://", "postgresql://")
    # autocommit=True is required by langgraph's setup() — it runs
    # CREATE INDEX CONCURRENTLY which cannot execute inside a transaction.
    # prepare_threshold=0 is required for PgBouncer compatibility.
    pool = AsyncConnectionPool(
        conninfo=conn_str,
        max_size=20,
        open=False,
        kwargs={"autocommit": True, "prepare_threshold": 0},
    )
    await pool.open()
    _checkpointer = AsyncPostgresSaver(pool)
    await _checkpointer.setup()


def make_thread_id(org_id: str, session_id: str) -> str:
    """Build a scoped LangGraph thread ID that prevents cross-org state access."""
    return f"{org_id}:{session_id}"
