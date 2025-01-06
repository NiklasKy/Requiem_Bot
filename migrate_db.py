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
    db_name = os.getenv("DB_NAME", "requiembot")
    db_user = os.getenv("DB_USER", "postgres")
    db_pass = os.getenv("DB_PASS", "postgres")
    
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
        
        # Connect to PostgreSQL
        logger.info("Connecting to PostgreSQL database...")
        engine = create_engine(get_db_url())
        Base.metadata.create_all(engine)
        Session = sessionmaker(bind=engine)
        pg_session = Session()
        
        # Migrate users
        logger.info("Migrating users...")
        sqlite_cursor.execute("SELECT discord_id, username, display_name, clan_role_id FROM users")
        users = sqlite_cursor.fetchall()
        
        for user_data in users:
            discord_id, username, display_name, clan_role_id = user_data
            user = User(
                discord_id=discord_id,
                username=username,
                display_name=display_name,
                clan_role_id=clan_role_id
            )
            pg_session.add(user)
        
        pg_session.commit()
        logger.info(f"Migrated {len(users)} users")
        
        # Migrate AFK entries
        logger.info("Migrating AFK entries...")
        sqlite_cursor.execute("""
            SELECT user_id, start_date, end_date, reason, is_active, 
                   created_at, ended_at
            FROM afk_users
        """)
        afk_entries = sqlite_cursor.fetchall()
        
        for afk_data in afk_entries:
            user_id, start_date, end_date, reason, is_active, created_at, ended_at = afk_data
            
            # Convert string dates to datetime objects
            start_date = datetime.fromisoformat(start_date)
            end_date = datetime.fromisoformat(end_date)
            created_at = datetime.fromisoformat(created_at) if created_at else datetime.utcnow()
            ended_at = datetime.fromisoformat(ended_at) if ended_at else None
            
            afk_entry = AFKEntry(
                user_id=user_id,
                start_date=start_date,
                end_date=end_date,
                reason=reason,
                is_active=bool(is_active),
                created_at=created_at,
                ended_at=ended_at
            )
            pg_session.add(afk_entry)
        
        pg_session.commit()
        logger.info(f"Migrated {len(afk_entries)} AFK entries")
        
        # Close connections
        sqlite_conn.close()
        pg_session.close()
        
        logger.info("Migration completed successfully!")
        
    except Exception as e:
        logger.error(f"Error during migration: {e}")
        raise

if __name__ == "__main__":
    migrate_data() 