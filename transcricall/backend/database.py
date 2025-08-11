from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from contextlib import contextmanager
import os


# Resolve a default database path relative to this file instead of relying on a
# hardcoded absolute location.  The previous implementation pointed to
# ``/workspace/transcricall`` which fails on systems where the repository is
# named differently (for example ``TranscriCall``).  By deriving the path from
# the package location we ensure the database can always be created.
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DEFAULT_DB_PATH = os.path.join(BASE_DIR, "transcricall.db")
DB_PATH = os.getenv("DB_PATH", DEFAULT_DB_PATH)

# Make sure the parent directory exists so SQLite can create the DB file.
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

DATABASE_URL = f"sqlite:///{DB_PATH}"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
    future=True,
)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


def init_db():
    from .models import Base
    Base.metadata.create_all(bind=engine)


@contextmanager
def get_session():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()