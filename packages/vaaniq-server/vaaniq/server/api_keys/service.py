from datetime import datetime, timezone
import httpx
import structlog
from sqlalchemy.ext.asyncio import AsyncSession
from vaaniq.server.core.encryption import encrypt_key, decrypt_key
from vaaniq.server.models.api_key import ApiKey
from vaaniq.server.api_keys.repository import ApiKeyRepository
from vaaniq.server.api_keys.schemas import (
    ApiKeyResponse,
    CreateApiKeyRequest,
    TestApiKeyResponse,
)
from vaaniq.server.api_keys.constants import _TESTABLE_SERVICES
from vaaniq.server.api_keys.exceptions import ApiKeyNotFound, ApiKeyAlreadyExists

log = structlog.get_logger()


def _mask_key(plaintext: str) -> str:
    """Return a hint like 'sk-****...ab' — never the full key."""
    if len(plaintext) <= 6:
        return "••••••••"
    return plaintext[:3] + "****..." + plaintext[-2:]


def _to_response(key: ApiKey, key_hint: str) -> ApiKeyResponse:
    return ApiKeyResponse(
        id=key.id,
        org_id=key.org_id,
        service=key.service,
        key_hint=key_hint,
        last_tested_at=key.last_tested_at,
        created_at=key.created_at,
    )


async def _test_openai(raw_key: str) -> TestApiKeyResponse:
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                "https://api.openai.com/v1/models",
                headers={"Authorization": f"Bearer {raw_key}"},
            )
        if resp.status_code == 200:
            return TestApiKeyResponse(valid=True, tested=True)
        return TestApiKeyResponse(valid=False, tested=True, error=f"HTTP {resp.status_code}")
    except Exception as e:
        return TestApiKeyResponse(valid=False, tested=True, error=str(e))


async def _test_anthropic(raw_key: str) -> TestApiKeyResponse:
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                "https://api.anthropic.com/v1/models",
                headers={
                    "x-api-key": raw_key,
                    "anthropic-version": "2023-06-01",
                },
            )
        if resp.status_code == 200:
            return TestApiKeyResponse(valid=True, tested=True)
        return TestApiKeyResponse(valid=False, tested=True, error=f"HTTP {resp.status_code}")
    except Exception as e:
        return TestApiKeyResponse(valid=False, tested=True, error=str(e))


class ApiKeyService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repo = ApiKeyRepository(db)

    async def create(self, org_id: str, data: CreateApiKeyRequest) -> ApiKeyResponse:
        existing = await self.repo.get_by_service(org_id, data.service)
        if existing:
            raise ApiKeyAlreadyExists(data.service)

        encrypted = encrypt_key(data.key)
        hint = _mask_key(data.key)

        key = await self.repo.create(org_id, data.service, encrypted)
        await self.db.commit()
        await self.db.refresh(key)

        log.info("api_key_created", org_id=org_id, service=data.service)
        return _to_response(key, hint)

    async def list(self, org_id: str) -> list[ApiKeyResponse]:
        keys = await self.repo.list_by_org(org_id)
        result = []
        for k in keys:
            try:
                hint = _mask_key(decrypt_key(k.encrypted_key))
            except Exception:
                hint = "••••••••"
            result.append(_to_response(k, hint))
        return result

    async def delete(self, key_id: str, org_id: str) -> None:
        key = await self.repo.get_by_id(key_id)
        if not key:
            raise ApiKeyNotFound()
        if key.org_id != org_id:
            raise ApiKeyNotFound()  # don't reveal existence to wrong org

        await self.repo.soft_delete(key_id)
        await self.db.commit()
        log.info("api_key_deleted", org_id=org_id, key_id=key_id)

    async def test(self, key_id: str, org_id: str) -> TestApiKeyResponse:
        key = await self.repo.get_by_id(key_id)
        if not key:
            raise ApiKeyNotFound()
        if key.org_id != org_id:
            raise ApiKeyNotFound()

        if key.service not in _TESTABLE_SERVICES:
            return TestApiKeyResponse(
                valid=True,
                tested=False,
                error="Live test not supported for this provider yet",
            )

        raw_key = decrypt_key(key.encrypted_key)

        if key.service == "openai":
            result = await _test_openai(raw_key)
        elif key.service == "anthropic":
            result = await _test_anthropic(raw_key)
        else:
            result = TestApiKeyResponse(valid=True, tested=False)

        if result.valid:
            await self.repo.update(key_id, last_tested_at=datetime.now(timezone.utc))
            await self.db.commit()

        log.info("api_key_tested", org_id=org_id, service=key.service, valid=result.valid)
        return result
