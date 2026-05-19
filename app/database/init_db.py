from app.database.models import Base
from app.database.seed import seed_demo_data
from app.database.session import SessionLocal, engine


def create_schema() -> None:
    Base.metadata.create_all(bind=engine)


def seed_database() -> None:
    with SessionLocal() as session:
        seed_demo_data(session)


def init_database() -> None:
    create_schema()
    seed_database()
