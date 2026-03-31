from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from vaaniq.server.core.config import settings


def add_cors(app: FastAPI) -> None:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
