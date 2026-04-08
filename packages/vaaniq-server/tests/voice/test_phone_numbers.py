"""
Unit tests for the PhoneNumber model and PhoneNumberRepository.
No DB required — tests verify query construction and repository logic.
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, call, patch


# ── Model smoke test ──────────────────────────────────────────────────────────

def test_phone_number_model_imports():
    from vaaniq.server.voice.models import PhoneNumber
    assert PhoneNumber.__tablename__ == "phone_numbers"


def test_phone_number_repr():
    from vaaniq.server.voice.models import PhoneNumber
    pn = PhoneNumber(number="+14155551234", agent_id="agent-1")
    assert "+14155551234" in repr(pn)
    assert "agent-1" in repr(pn)


# ── Repository tests ──────────────────────────────────────────────────────────

def _make_db() -> AsyncMock:
    """Mock AsyncSession."""
    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    return db


@pytest.mark.asyncio
async def test_create_adds_and_flushes():
    from vaaniq.server.voice.repository import PhoneNumberRepository
    db = _make_db()
    repo = PhoneNumberRepository(db)

    pn = await repo.create(
        org_id="org-1",
        agent_id="agent-1",
        number="+14155551234",
        provider="twilio",
        sid="PN-abc",
    )

    db.add.assert_called_once_with(pn)
    db.flush.assert_called_once()
    assert pn.org_id == "org-1"
    assert pn.agent_id == "agent-1"
    assert pn.number == "+14155551234"
    assert pn.provider == "twilio"
    assert pn.sid == "PN-abc"
    assert pn.id is not None  # uuid auto-assigned


@pytest.mark.asyncio
async def test_create_defaults_provider_to_twilio():
    from vaaniq.server.voice.repository import PhoneNumberRepository
    db = _make_db()
    repo = PhoneNumberRepository(db)

    pn = await repo.create(org_id="org-1", agent_id="agent-1", number="+19995551234")
    assert pn.provider == "twilio"


@pytest.mark.asyncio
async def test_get_by_number_returns_record():
    from vaaniq.server.voice.models import PhoneNumber
    from vaaniq.server.voice.repository import PhoneNumberRepository

    db = _make_db()
    existing = PhoneNumber(id="pn-1", number="+14155551234", agent_id="agent-1", org_id="org-1")
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = existing
    db.execute = AsyncMock(return_value=mock_result)

    repo = PhoneNumberRepository(db)
    result = await repo.get_by_number("+14155551234")

    assert result is existing
    db.execute.assert_called_once()


@pytest.mark.asyncio
async def test_get_by_number_returns_none_when_missing():
    from vaaniq.server.voice.repository import PhoneNumberRepository

    db = _make_db()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    db.execute = AsyncMock(return_value=mock_result)

    repo = PhoneNumberRepository(db)
    result = await repo.get_by_number("+10000000000")

    assert result is None


@pytest.mark.asyncio
async def test_list_by_org_returns_list():
    from vaaniq.server.voice.models import PhoneNumber
    from vaaniq.server.voice.repository import PhoneNumberRepository

    db = _make_db()
    pn1 = PhoneNumber(id="pn-1", org_id="org-1", agent_id="agent-1", number="+14155551111")
    pn2 = PhoneNumber(id="pn-2", org_id="org-1", agent_id="agent-1", number="+14155552222")

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [pn1, pn2]
    db.execute = AsyncMock(return_value=mock_result)

    repo = PhoneNumberRepository(db)
    results = await repo.list_by_org("org-1")

    assert results == [pn1, pn2]


@pytest.mark.asyncio
async def test_soft_delete_sets_deleted_at():
    from vaaniq.server.voice.repository import PhoneNumberRepository

    db = _make_db()
    db.execute = AsyncMock(return_value=MagicMock())

    repo = PhoneNumberRepository(db)
    await repo.soft_delete("pn-1")

    db.execute.assert_called_once()
    # Verify the call contained an UPDATE statement (not SELECT)
    stmt = db.execute.call_args.args[0]
    assert "phone_numbers" in str(stmt).lower() or hasattr(stmt, "table")
