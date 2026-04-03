import json
from datetime import datetime, timezone
import httpx
import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from vaaniq.core.credentials import CredentialStore
from vaaniq.tools.providers import build_org_keys as _build_value
from vaaniq.server.core.encryption import encrypt_key, decrypt_key
from vaaniq.server.models.integration import Integration
from vaaniq.server.integrations.repository import IntegrationRepository
from vaaniq.server.integrations.constants import PROVIDERS, _TESTABLE_PROVIDERS
from vaaniq.server.integrations.schemas import (
    CreateIntegrationRequest,
    IntegrationResponse,
    TestIntegrationResponse,
)
from vaaniq.server.integrations.exceptions import (
    IntegrationNotFound,
    IntegrationAlreadyExists,
)

log = structlog.get_logger()


def _make_key_hint(credentials: dict) -> str:
    """Return a masked hint for a single api_key credential, empty string otherwise."""
    key = credentials.get("api_key", "")
    if not key or len(key) <= 6:
        return ""
    return key[:4] + "····" + key[-4:]


def _to_response(integration: Integration) -> IntegrationResponse:
    return IntegrationResponse(
        id=integration.id,
        org_id=integration.org_id,
        provider=integration.provider,
        category=integration.category,
        display_name=integration.display_name,
        config=integration.config or {},
        status=integration.status,
        meta=integration.meta or {},
        created_at=integration.created_at,
    )


async def _test_openai(api_key: str) -> TestIntegrationResponse:
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                "https://api.openai.com/v1/models",
                headers={"Authorization": f"Bearer {api_key}"},
            )
        if resp.status_code == 200:
            return TestIntegrationResponse(valid=True, tested=True)
        return TestIntegrationResponse(valid=False, tested=True, error=f"HTTP {resp.status_code}")
    except Exception as e:
        return TestIntegrationResponse(valid=False, tested=True, error=str(e))


async def _test_anthropic(api_key: str) -> TestIntegrationResponse:
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                "https://api.anthropic.com/v1/models",
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                },
            )
        if resp.status_code == 200:
            return TestIntegrationResponse(valid=True, tested=True)
        return TestIntegrationResponse(valid=False, tested=True, error=f"HTTP {resp.status_code}")
    except Exception as e:
        return TestIntegrationResponse(valid=False, tested=True, error=str(e))


class PostgresCredentialStore(CredentialStore):
    """CredentialStore backed by the integrations table.

    This is the production, multi-tenant implementation.
    Credentials are Fernet-encrypted in PostgreSQL — one row per (org, provider).

    Used by chat/service.py and (future) voice pipeline at session start.
    Standalone developers who don't use vaaniq-server should use
    vaaniq-tools EnvCredentialStore instead.
    """

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get_org_keys(self, org_id: str) -> dict:
        """Return decrypted org_keys for all active integrations belonging to org_id."""
        integrations = await IntegrationRepository(self._db).list_by_org(org_id)
        org_keys: dict = {}
        for integration in integrations:
            try:
                creds = json.loads(decrypt_key(integration.credentials))
            except Exception:
                continue
            org_keys[integration.provider] = _build_value(
                integration.provider, creds, integration.config or {}
            )
        return org_keys


# Keep this as a convenience function used directly by chat/service.py
async def build_org_keys(integrations: list[Integration]) -> dict:
    """Build org_keys from a pre-fetched list of Integration rows.

    Prefer PostgresCredentialStore.get_org_keys() for new code — this helper
    exists so chat/service.py doesn't need to instantiate the store class.
    """
    org_keys: dict = {}
    for integration in integrations:
        try:
            creds = json.loads(decrypt_key(integration.credentials))
        except Exception:
            continue
        org_keys[integration.provider] = _build_value(
            integration.provider, creds, integration.config or {}
        )
    return org_keys


class IntegrationService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repo = IntegrationRepository(db)

    async def create(self, org_id: str, data: CreateIntegrationRequest) -> IntegrationResponse:
        existing = await self.repo.get_by_provider(org_id, data.provider)
        if existing:
            raise IntegrationAlreadyExists(data.provider)

        provider_meta = PROVIDERS[data.provider]
        encrypted = encrypt_key(json.dumps(data.credentials))

        integration = await self.repo.create(
            org_id=org_id,
            provider=data.provider,
            category=provider_meta["category"],
            display_name=data.display_name,
            credentials=encrypted,
            config=data.config,
        )
        await self.db.commit()
        await self.db.refresh(integration)

        # Store a masked hint so the frontend can show something without decrypting
        key_hint = _make_key_hint(data.credentials)
        if key_hint:
            await self.repo.update(integration.id, meta={"key_hint": key_hint})
            await self.db.commit()
            await self.db.refresh(integration)

        log.info("integration_created", org_id=org_id, provider=data.provider)
        return _to_response(integration)

    async def list(self, org_id: str) -> list[IntegrationResponse]:
        integrations = await self.repo.list_by_org(org_id)
        return [_to_response(i) for i in integrations]

    async def delete(self, integration_id: str, org_id: str) -> None:
        integration = await self.repo.get_by_id(integration_id)
        if not integration or integration.org_id != org_id:
            raise IntegrationNotFound()

        await self.repo.soft_delete(integration_id)
        await self.db.commit()
        log.info("integration_deleted", org_id=org_id, integration_id=integration_id)

    async def test(self, integration_id: str, org_id: str) -> TestIntegrationResponse:
        integration = await self.repo.get_by_id(integration_id)
        if not integration or integration.org_id != org_id:
            raise IntegrationNotFound()

        if integration.provider not in _TESTABLE_PROVIDERS:
            return TestIntegrationResponse(
                valid=True,
                tested=False,
                error="Live test not supported for this provider yet",
            )

        creds = json.loads(decrypt_key(integration.credentials))

        if integration.provider == "openai":
            result = await _test_openai(creds.get("api_key", ""))
        elif integration.provider == "anthropic":
            result = await _test_anthropic(creds.get("api_key", ""))
        else:
            result = TestIntegrationResponse(valid=True, tested=False)

        if result.valid:
            await self.repo.update(integration_id, meta={
                **(integration.meta or {}),
                "last_tested_at": datetime.now(timezone.utc).isoformat(),
            })
            await self.db.commit()

        log.info("integration_tested", org_id=org_id, provider=integration.provider, valid=result.valid)
        return result
