from fastapi import FastAPI
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import sessionmaker

from app.api.v1.ecommerce_ops.routes import get_db_session, router
from app.database.models import Base
from app.database.seed import seed_demo_data
from app.security.api_key import require_api_key


async def allow_test_request() -> None:
    return None


def create_test_app(disable_auth: bool = True) -> FastAPI:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine)
    seed_session = session_factory()
    try:
        seed_demo_data(seed_session)
    finally:
        seed_session.close()

    def override_db_session():
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[get_db_session] = override_db_session
    if disable_auth:
        app.dependency_overrides[require_api_key] = allow_test_request
    return app
