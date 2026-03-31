from fastapi import HTTPException, status


class EmailAlreadyExists(HTTPException):
    def __init__(self) -> None:
        super().__init__(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")


class InvalidCredentials(HTTPException):
    def __init__(self) -> None:
        super().__init__(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")


class InvalidToken(HTTPException):
    def __init__(self, detail: str = "Invalid token") -> None:
        super().__init__(status_code=status.HTTP_401_UNAUTHORIZED, detail=detail)
