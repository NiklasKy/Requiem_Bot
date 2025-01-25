"""Database connection handling."""
import os
import time
from typing import Generator
from contextlib import contextmanager
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import QueuePool

from src.database.models import Base

# Get database connection details from environment variables
DB_HOST = os.getenv("DB_HOST")  # Use value from .env file
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "requiem_bot")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "postgres")

# Construct database URL
DATABASE_URL = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

def wait_for_db(retries: int = 5, delay: int = 5) -> None:
    """Wait for database to become available."""
    import psycopg2
    for i in range(retries):
        try:
            conn = psycopg2.connect(
                dbname=DB_NAME,
                user=DB_USER,
                password=DB_PASSWORD,
                host=DB_HOST,
                port=DB_PORT
            )
            conn.close()
            print("Database is ready!")
            return
        except psycopg2.OperationalError:
            if i < retries - 1:
                print(f"Database not ready, retrying in {delay} seconds...")
                time.sleep(delay)
            else:
                raise Exception("Could not connect to database after multiple retries")

# Create database engine
engine = create_engine(DATABASE_URL)

# Create session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def init_db() -> None:
    """Initialize the database by creating all tables."""
    wait_for_db()
    Base.metadata.create_all(bind=engine)

@contextmanager
def get_db_session() -> Session:
    """Get a database session."""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

def get_db() -> Generator[Session, None, None]:
    """Get a database session for FastAPI dependency injection.
    
    Yields:
        Session: Database session
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close() 