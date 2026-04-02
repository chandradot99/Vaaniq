from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession
from vaaniq.server.core.database import get_db
from vaaniq.server.auth.dependencies import get_current_user, CurrentUser
from vaaniq.server.api_keys.dependencies import valid_api_key
from vaaniq.server.models.api_key import ApiKey
from vaaniq.server.api_keys.service import ApiKeyService
from vaaniq.server.api_keys.schemas import (
    ApiKeyResponse,
    CreateApiKeyRequest,
    TestApiKeyResponse,
)

router = APIRouter(prefix="/v1/api-keys", tags=["api-keys"])


@router.post("", response_model=ApiKeyResponse, status_code=status.HTTP_201_CREATED)
async def create_api_key(
    body: CreateApiKeyRequest,
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApiKeyResponse:
    return await ApiKeyService(db).create(current.org_id, body)


@router.get("", response_model=list[ApiKeyResponse])
async def list_api_keys(
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ApiKeyResponse]:
    return await ApiKeyService(db).list(current.org_id)


@router.delete("/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_api_key(
    current: CurrentUser = Depends(get_current_user),
    key: ApiKey = Depends(valid_api_key),
    db: AsyncSession = Depends(get_db),
) -> None:
    await ApiKeyService(db).delete(key.id, current.org_id)


@router.post("/{key_id}/test", response_model=TestApiKeyResponse)
async def test_api_key(
    current: CurrentUser = Depends(get_current_user),
    key: ApiKey = Depends(valid_api_key),
    db: AsyncSession = Depends(get_db),
) -> TestApiKeyResponse:
    return await ApiKeyService(db).test(key.id, current.org_id)
