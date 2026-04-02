from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession
from vaaniq.server.core.database import get_db
from vaaniq.server.auth.dependencies import get_current_user, CurrentUser
from vaaniq.server.models.api_key import ApiKey
from vaaniq.server.api_keys.repository import ApiKeyRepository
from vaaniq.server.api_keys.exceptions import ApiKeyNotFound


async def valid_api_key(
    key_id: str,
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApiKey:
    """Fetch and validate that key_id exists and belongs to the current org."""
    key = await ApiKeyRepository(db).get_by_id(key_id)
    if not key or key.org_id != current.org_id:
        raise ApiKeyNotFound()
    return key
