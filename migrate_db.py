"""Script to migrate data from SQLite to PostgreSQL."""
import sqlite3
import logging
from datetime import datetime
import os

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

from src.database.models import Base, User, AFKEntry

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

def get_db_url():
    """Get database URL from environment variables."""
    db_host = os.getenv("DB_HOST", "db")
    db_port = os.getenv("DB_PORT", "5432")
    db_name = os.getenv("DB_NAME", "postgres")
    db_user = os.getenv("DB_USER", "postgres")
    db_pass = os.getenv("DB_PASSWORD", "postgres")
    
    logger.info(f"Connecting to PostgreSQL at {db_host}:{db_port} as {db_user}")
    return f"postgresql://{db_user}:{db_pass}@{db_host}:{db_port}/{db_name}"

def migrate_data():
    """Migrate data from SQLite to PostgreSQL."""
    try:
        # Connect to SQLite database
        sqlite_path = "database.db"  # SQLite database file in the same directory
        if not os.path.exists(sqlite_path):
            raise FileNotFoundError(f"SQLite database file not found at {sqlite_path}")
            
        logger.info("Connecting to SQLite database...")
        sqlite_conn = sqlite3.connect(sqlite_path)
        sqlite_cursor = sqlite_conn.cursor()
        
        # Get table names
        sqlite_cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = sqlite_cursor.fetchall()
        logger.info("Found tables in SQLite database:")
        for table in tables:
            logger.info(f"- {table[0]}")
            # Get table schema
            sqlite_cursor.execute(f"PRAGMA table_info({table[0]})")
            columns = sqlite_cursor.fetchall()
            for col in columns:
                logger.info(f"  - {col[1]} ({col[2]})")
        
        # Connect to PostgreSQL
        logger.info("Connecting to PostgreSQL database...")
        engine = create_engine(get_db_url())
        Base.metadata.create_all(engine)
        Session = sessionmaker(bind=engine)
        pg_session = Session()
        
        # Close connections
        sqlite_conn.close()
        pg_session.close()
        
        logger.info("Database inspection completed!")
        
    except Exception as e:
        logger.error(f"Error during migration: {e}")
        raise

if __name__ == "__main__":
    migrate_data() 