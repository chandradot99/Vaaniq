SUPPORTED_SERVICES = [
    # LLM
    "openai",
    "anthropic",
    "gemini",
    "groq",
    "azure_openai",
    "mistral",
    # STT
    "deepgram",
    "assemblyai",
    "sarvam",
    # TTS
    "elevenlabs",
    "cartesia",
    # Telephony
    "twilio",
    "vonage",
    "telnyx",
    # WhatsApp
    "gupshup",
    # Vector DB (pgvector is the default — no key needed)
    "pinecone",
    "qdrant",
]

# Services with live test support
_TESTABLE_SERVICES = {"openai", "anthropic"}
