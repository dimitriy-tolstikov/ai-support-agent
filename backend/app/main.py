"""демонстрирует: сборку FastAPI-приложения — lifespan (пул БД, воркер очереди), роутеры /api/v1."""
import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api import conversations, webhooks
from .db import close_pool, init_pool
from .queue import worker

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_pool()
    worker_task = asyncio.create_task(worker())
    yield
    worker_task.cancel()
    await close_pool()


app = FastAPI(title="AI Support Agent", version="1.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.include_router(conversations.router)
app.include_router(webhooks.router)


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}
