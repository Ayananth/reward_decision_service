from fastapi import FastAPI

from app.routers.reward import router as reward_router


def create_app() -> FastAPI:
    app = FastAPI(title="Reward Decision Service")
    app.include_router(reward_router)
    return app
