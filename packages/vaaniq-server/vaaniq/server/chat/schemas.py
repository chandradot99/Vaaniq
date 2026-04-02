from vaaniq.server.core.schemas import CustomModel


class ChatMessage(CustomModel):
    role: str       # "agent" | "user"
    content: str


class StartChatResponse(CustomModel):
    session_id: str
    messages: list[ChatMessage]
    session_ended: bool = False


class SendMessageRequest(CustomModel):
    session_id: str
    message: str


class SendMessageResponse(CustomModel):
    messages: list[ChatMessage]   # new messages since last turn (agent only)
    session_ended: bool = False
