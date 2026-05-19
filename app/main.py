from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.v1.ecommerce_ops.routes import router as ecommerce_ops_router
from app.database.init_db import init_database


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_database()
    yield


app = FastAPI(
    title="Agentic E-Commerce Operations Manager",
    version="0.1.0",
    description="Backend-first multi-agent e-commerce operations manager.",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

app.include_router(ecommerce_ops_router, prefix="/api/v1")


@app.get("/")
async def root():
    return {
        "service": "agentic-ecommerce-ops-manager",
        "version": "0.1.0",
        "docs": "/docs",
        "health": "/api/v1/ecommerce-ops/health",
    }
