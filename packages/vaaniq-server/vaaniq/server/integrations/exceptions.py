from vaaniq.server.exceptions import Conflict, NotFound


class IntegrationNotFound(NotFound):
    def __init__(self) -> None:
        super().__init__("Integration not found")


class IntegrationAlreadyExists(Conflict):
    def __init__(self, provider: str) -> None:
        super().__init__(f"An integration for '{provider}' already exists. Delete it first to re-add.")
