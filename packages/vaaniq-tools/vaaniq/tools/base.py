from abc import ABC, abstractmethod


class BaseTool(ABC):
    """Base class for all pre-built Vaaniq tools.

    Subclasses declare:
        name                 — unique key used in run_tool node config and TOOL_REGISTRY
        description          — shown to LLM and in the graph builder UI tool picker
        input_schema         — JSON Schema for the tool's input fields
        required_integration — provider key that must exist in org_keys (or None)

    The run() method receives:
        input     — resolved input dict (template vars already substituted)
        org_keys  — decrypted credentials for the org (from integrations table)
    """
    name: str
    description: str
    input_schema: dict
    required_integration: str | None = None

    @abstractmethod
    async def run(self, input: dict, org_keys: dict) -> dict:
        """Execute the tool and return a result dict."""
        ...

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
            "required_integration": self.required_integration,
        }
