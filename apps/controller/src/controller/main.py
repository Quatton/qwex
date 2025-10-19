from contextlib import asynccontextmanager

from fastapi import FastAPI

from controller.config import kube


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup/shutdown."""
    # Startup
    kube.setup()
    yield
    # Shutdown (nothing to do for now)


app = FastAPI(lifespan=lifespan)


@app.get("/")
async def read_root():
    return {"Hello": "World"}
