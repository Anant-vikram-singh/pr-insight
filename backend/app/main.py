from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.core.config import Settings, get_settings
from app.services.github_service import GitHubService
from app.services.llm_provider import GroqProvider
from app.services.review_service import ReviewEngine


def create_app(settings: Settings | None = None) -> FastAPI:
    configured_settings = settings or get_settings()
    # Uvicorn's default root logger is WARNING. Keep the review-response
    # diagnostics visible at INFO without changing logging levels globally.
    review_logger = logging.getLogger("app.services.review_service")
    review_logger.setLevel(logging.INFO)
    uvicorn_logger = logging.getLogger("uvicorn")
    if uvicorn_logger.handlers and not review_logger.handlers:
        review_logger.handlers.extend(uvicorn_logger.handlers)
        review_logger.propagate = False

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        service = GitHubService(configured_settings)
        app.state.github_service = service
        app.state.review_engine = ReviewEngine(
            service, GroqProvider(configured_settings), configured_settings
        )
        yield
        await service.close()

    app = FastAPI(title="PR Insight API", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "https://pr-insight-gold.vercel.app",
            "http://localhost:5173",
            "http://127.0.0.1:5173",
        ],
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type"],
    )
    app.include_router(router)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()

