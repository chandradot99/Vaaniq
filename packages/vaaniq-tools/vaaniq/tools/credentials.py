"""EnvCredentialStore — credential store for standalone developer use.

Reads credentials from environment variables. No database, no server needed.
Designed for developers using vaaniq-tools directly in their own apps.

Usage:
    from vaaniq.tools.credentials import EnvCredentialStore

    store = EnvCredentialStore()
    org_keys = await store.get_org_keys("any_org_id")  # org_id ignored for env store

    result = await TOOL_REGISTRY["google_calendar_create_event"].run(input, org_keys)

Environment variables follow this convention:
    Simple providers (LLM, STT, TTS):
        OPENAI_API_KEY, ANTHROPIC_API_KEY, DEEPGRAM_API_KEY, ...

    Google (Calendar + Gmail):
        GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_REFRESH_TOKEN

    Pinecone:
        PINECONE_API_KEY, PINECONE_ENVIRONMENT, PINECONE_INDEX_NAME

    Twilio:
        TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN
"""
import os
from vaaniq.core.credentials import CredentialStore


class EnvCredentialStore(CredentialStore):
    """Loads credentials from environment variables.

    Useful for:
    - Local development and testing without a database
    - CLI tools and scripts built on vaaniq-tools
    - Single-tenant self-hosted deployments where env vars are sufficient

    Not suitable for multi-tenant production (all orgs share the same env vars).
    Use vaaniq-server's PostgresCredentialStore for multi-tenant use.
    """

    async def get_org_keys(self, org_id: str = "") -> dict:
        """Build org_keys from environment variables.

        org_id is accepted but ignored — EnvCredentialStore is single-tenant.
        """
        org_keys: dict = {}

        # ── LLM ──────────────────────────────────────────────────────────────
        if key := os.environ.get("OPENAI_API_KEY"):
            org_keys["openai"] = key
        if key := os.environ.get("ANTHROPIC_API_KEY"):
            org_keys["anthropic"] = key
        if key := os.environ.get("GEMINI_API_KEY"):
            org_keys["gemini"] = key
        if key := os.environ.get("GROQ_API_KEY"):
            org_keys["groq"] = key
        if key := os.environ.get("MISTRAL_API_KEY"):
            org_keys["mistral"] = key

        azure_key = os.environ.get("AZURE_OPENAI_API_KEY")
        if azure_key:
            org_keys["azure_openai"] = {
                "api_key": azure_key,
                "endpoint": os.environ.get("AZURE_OPENAI_ENDPOINT", ""),
                "deployment": os.environ.get("AZURE_OPENAI_DEPLOYMENT", ""),
                "api_version": os.environ.get("AZURE_OPENAI_API_VERSION", "2024-02-01"),
            }

        # ── STT ──────────────────────────────────────────────────────────────
        if key := os.environ.get("DEEPGRAM_API_KEY"):
            org_keys["deepgram"] = key
        if key := os.environ.get("ASSEMBLYAI_API_KEY"):
            org_keys["assemblyai"] = key
        if key := os.environ.get("SARVAM_API_KEY"):
            org_keys["sarvam"] = key

        # ── TTS ──────────────────────────────────────────────────────────────
        if key := os.environ.get("ELEVENLABS_API_KEY"):
            org_keys["elevenlabs"] = key
        if key := os.environ.get("CARTESIA_API_KEY"):
            org_keys["cartesia"] = key

        # ── Telephony ─────────────────────────────────────────────────────────
        twilio_sid = os.environ.get("TWILIO_ACCOUNT_SID")
        twilio_token = os.environ.get("TWILIO_AUTH_TOKEN")
        if twilio_sid and twilio_token:
            org_keys["twilio"] = {"account_sid": twilio_sid, "auth_token": twilio_token}

        # ── Google (Calendar + Gmail + Sheets + Drive) ─────────────────────
        google_client_id = os.environ.get("GOOGLE_CLIENT_ID")
        google_client_secret = os.environ.get("GOOGLE_CLIENT_SECRET")
        google_refresh_token = os.environ.get("GOOGLE_REFRESH_TOKEN")
        if google_client_id and google_client_secret and google_refresh_token:
            org_keys["google"] = {
                "client_id": google_client_id,
                "client_secret": google_client_secret,
                "refresh_token": google_refresh_token,
                "access_token": os.environ.get("GOOGLE_ACCESS_TOKEN"),
            }

        # ── HubSpot ───────────────────────────────────────────────────────────
        if key := os.environ.get("HUBSPOT_ACCESS_TOKEN"):
            org_keys["hubspot"] = {"access_token": key}

        # ── Slack ─────────────────────────────────────────────────────────────
        if key := os.environ.get("SLACK_BOT_TOKEN"):
            org_keys["slack"] = {"bot_token": key}

        # ── Razorpay ──────────────────────────────────────────────────────────
        razorpay_id = os.environ.get("RAZORPAY_KEY_ID")
        razorpay_secret = os.environ.get("RAZORPAY_KEY_SECRET")
        if razorpay_id and razorpay_secret:
            org_keys["razorpay"] = {"key_id": razorpay_id, "key_secret": razorpay_secret}

        # ── Stripe ────────────────────────────────────────────────────────────
        if key := os.environ.get("STRIPE_SECRET_KEY"):
            org_keys["stripe"] = {"secret_key": key}

        # ── Pinecone ──────────────────────────────────────────────────────────
        pinecone_key = os.environ.get("PINECONE_API_KEY")
        if pinecone_key:
            org_keys["pinecone"] = {
                "api_key": pinecone_key,
                "environment": os.environ.get("PINECONE_ENVIRONMENT", ""),
                "index_name": os.environ.get("PINECONE_INDEX_NAME", ""),
            }

        # ── Qdrant ────────────────────────────────────────────────────────────
        qdrant_key = os.environ.get("QDRANT_API_KEY")
        if qdrant_key:
            org_keys["qdrant"] = {
                "api_key": qdrant_key,
                "url": os.environ.get("QDRANT_URL", ""),
                "collection_name": os.environ.get("QDRANT_COLLECTION_NAME", ""),
            }

        # ── Redis ─────────────────────────────────────────────────────────────
        if url := os.environ.get("REDIS_URL"):
            org_keys["redis"] = {
                "url": url,
                "password": os.environ.get("REDIS_PASSWORD", ""),
            }

        return org_keys
