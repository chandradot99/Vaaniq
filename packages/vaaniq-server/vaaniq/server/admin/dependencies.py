from fastapi import Depends
from vaaniq.server.auth.dependencies import get_current_user, CurrentUser
from vaaniq.server.admin.exceptions import AdminOnly


async def require_owner(current: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    """Only org owners can access admin endpoints."""
    if current.role != "owner":
        raise AdminOnly()
    return current
