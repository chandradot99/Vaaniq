from fastapi import HTTPException, status


class ChatSessionNotFound(HTTPException):
    def __init__(self) -> None:
        super().__init__(status_code=status.HTTP_404_NOT_FOUND, detail="Chat session not found or expired")


class ChatSessionEnded(HTTPException):
    def __init__(self) -> None:
        super().__init__(status_code=status.HTTP_400_BAD_REQUEST, detail="Chat session has already ended")
