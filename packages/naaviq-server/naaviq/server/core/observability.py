import os

import sentry_sdk
import structlog
from sentry_sdk.integrations.fastapi import FastApiIntegration

from naaviq.server.core.config import settings


def setup_observability() -> None:
    # Push LangSmith vars into os.environ so LangChain picks them up automatically.
    # pydantic-settings reads .env into Python attributes but does NOT set os.environ.
    if settings.langsmith_api_key:
        os.environ["LANGSMITH_API_KEY"] = settings.langsmith_api_key
        os.environ["LANGSMITH_TRACING"] = settings.langsmith_tracing
        os.environ["LANGSMITH_ENDPOINT"] = settings.langsmith_endpoint
        os.environ["LANGSMITH_PROJECT"] = settings.langsmith_project

    if settings.sentry_dsn:
        sentry_sdk.init(
            dsn=settings.sentry_dsn,
            integrations=[FastApiIntegration()],
            environment=settings.environment,
            traces_sample_rate=0.2,
        )

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(20),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
    )
