from fastapi import HTTPException, status
from vaaniq.server.exceptions import NotFound


class ApiKeyNotFound(NotFound):
    def __init__(self) -> None:
        super().__init__("API key not found")


class ApiKeyAlreadyExists(HTTPException):
    def __init__(self, service: str) -> None:
        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"An API key for '{service}' already exists. Delete it first to replace.",
        )
