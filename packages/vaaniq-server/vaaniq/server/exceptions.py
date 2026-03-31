from fastapi import HTTPException, status


class VaaniqException(HTTPException):
    """Base exception for all Vaaniq HTTP errors."""
    pass


class NotFound(VaaniqException):
    def __init__(self, detail: str = "Resource not found") -> None:
        super().__init__(status_code=status.HTTP_404_NOT_FOUND, detail=detail)


class Unauthorized(VaaniqException):
    def __init__(self, detail: str = "Unauthorized") -> None:
        super().__init__(status_code=status.HTTP_401_UNAUTHORIZED, detail=detail)
