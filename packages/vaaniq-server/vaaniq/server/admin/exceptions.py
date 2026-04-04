from fastapi import HTTPException, status


class ProviderNotFound(HTTPException):
    def __init__(self) -> None:
        super().__init__(status_code=status.HTTP_404_NOT_FOUND, detail="Provider not found")


class UnknownProvider(HTTPException):
    def __init__(self, provider: str) -> None:
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown provider '{provider}'. Add it to PLATFORM_PROVIDER_SCHEMAS first.",
        )


class AdminOnly(HTTPException):
    def __init__(self) -> None:
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
