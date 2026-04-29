from naaviq.server.exceptions import NotFound, Unauthorized


class AgentNotFound(NotFound):
    def __init__(self) -> None:
        super().__init__("Agent not found")


class AgentAccessDenied(Unauthorized):
    def __init__(self) -> None:
        super().__init__("You do not have access to this agent")
