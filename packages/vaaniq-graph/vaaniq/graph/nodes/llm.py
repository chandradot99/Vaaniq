"""Shared LLM provider factory for graph nodes."""
from langchain_anthropic import ChatAnthropic
from langchain_openai import ChatOpenAI
from langchain_core.language_models import BaseChatModel


def get_llm(config: dict, org_keys: dict) -> BaseChatModel:
    """
    Return a LangChain chat model based on node config and available org keys.

    Config fields (all optional):
        provider  (str)  "openai" | "anthropic" — auto-detected from org_keys if omitted
        model     (str)  model name, e.g. "gpt-4o" or "claude-3-5-sonnet-20241022"
        temperature (float)  default 0.7
    """
    provider: str = config.get("provider", "").lower()
    temperature: float = float(config.get("temperature", 0.7))

    # Auto-detect provider from available keys if not explicitly set
    if not provider:
        if org_keys.get("openai"):
            provider = "openai"
        elif org_keys.get("anthropic"):
            provider = "anthropic"
        else:
            raise ValueError(
                "No LLM provider configured. Add an OpenAI or Anthropic key in API Keys settings."
            )

    if provider == "openai":
        return ChatOpenAI(
            api_key=org_keys["openai"],
            model=config.get("model", "gpt-4o-mini"),
            temperature=temperature,
        )

    if provider == "anthropic":
        return ChatAnthropic(
            api_key=org_keys["anthropic"],
            model=config.get("model", "claude-3-5-haiku-20241022"),
            temperature=temperature,
        )

    raise ValueError(f"Unsupported LLM provider: {provider!r}")
