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

    def normalize_input(self, inputs: dict) -> dict:
        """Coerce inputs to match input_schema types. Override for additional validation.

        Called by run_tool node after template resolution and before required-field check.
        Raise ValueError with a user-readable message to fail fast with a clear error.
        """
        schema_props: dict = (self.input_schema or {}).get("properties", {})
        result = dict(inputs)
        for field, spec in schema_props.items():
            if field not in result or result[field] is None:
                continue
            expected_type = spec.get("type")
            try:
                if expected_type == "integer":
                    result[field] = int(result[field])
                elif expected_type == "number":
                    result[field] = float(result[field])
                elif expected_type == "boolean" and isinstance(result[field], str):
                    result[field] = result[field].lower() in ("true", "yes", "1")
            except (ValueError, TypeError):
                pass  # leave as-is — required-field check or the tool itself will surface the error
        return result

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
