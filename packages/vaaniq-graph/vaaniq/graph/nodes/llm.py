"""Shared LLM provider factory for graph nodes."""
from langchain_anthropic import ChatAnthropic
from langchain_core.language_models import BaseChatModel
from langchain_openai import ChatOpenAI


def get_llm(config: dict, org_keys: dict) -> BaseChatModel:
    """
    Return a LangChain chat model based on node config and available org keys.

    Config fields (all optional):
        provider    (str)   "openai" | "anthropic" | "groq" | "gemini" | "mistral"
                            Auto-detected from org_keys if omitted.
        model       (str)   Model name, e.g. "gpt-4o-mini" or "claude-sonnet-4-6"
        temperature (float) Default 0.7
    """
    provider: str = config.get("provider", "").lower()
    model: str = config.get("model", "")
    temperature: float = float(config.get("temperature", 0.7))

    # Auto-detect provider from available keys if not explicitly set
    if not provider:
        if org_keys.get("openai"):
            provider = "openai"
        elif org_keys.get("anthropic"):
            provider = "anthropic"
        elif org_keys.get("groq"):
            provider = "groq"
        elif org_keys.get("gemini"):
            provider = "gemini"
        elif org_keys.get("mistral"):
            provider = "mistral"
        else:
            raise ValueError(
                "No LLM provider configured. Add an API key in Settings → API Keys."
            )

    if provider == "openai":
        return ChatOpenAI(
            api_key=org_keys.get("openai"),
            model=model or "gpt-4o-mini",
            temperature=temperature,
            streaming=True,
        )

    if provider == "anthropic":
        return ChatAnthropic(
            api_key=org_keys.get("anthropic"),
            model=model or "claude-3-5-haiku-20241022",
            temperature=temperature,
            streaming=True,
        )

    if provider == "groq":
        try:
            from langchain_groq import ChatGroq
        except ImportError as e:
            raise ImportError("Install langchain-groq: uv add langchain-groq") from e
        return ChatGroq(
            api_key=org_keys.get("groq"),
            model=model or "llama-3.1-8b-instant",
            temperature=temperature,
        )

    if provider == "gemini":
        try:
            from langchain_google_genai import ChatGoogleGenerativeAI
        except ImportError as e:
            raise ImportError("Install langchain-google-genai: uv add langchain-google-genai") from e
        return ChatGoogleGenerativeAI(
            google_api_key=org_keys.get("gemini"),
            model=model or "gemini-1.5-flash",
            temperature=temperature,
        )

    if provider == "mistral":
        try:
            from langchain_mistralai import ChatMistralAI
        except ImportError as e:
            raise ImportError("Install langchain-mistralai: uv add langchain-mistralai") from e
        return ChatMistralAI(
            api_key=org_keys.get("mistral"),
            model=model or "mistral-small-latest",
            temperature=temperature,
        )

    raise ValueError(
        f"Unsupported LLM provider: {provider!r}. "
        "Valid options: openai, anthropic, groq, gemini, mistral"
    )
