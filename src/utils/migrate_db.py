"""Script to migrate data from SQLite to PostgreSQL."""
import sqlite3
import logging
from datetime import datetime
import os

from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import sessionmaker, Session
from dotenv import load_dotenv

from src.database.models import Base, User, AFKEntry, GuildInfo
from src.database.connection import DATABASE_URL

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()]
)
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

def add_is_deleted_column():
    """Add is_deleted column to afk_entries table if it doesn't exist."""
    try:
        engine = create_engine(get_db_url())
        with engine.connect() as connection:
            # Check if column exists
            result = connection.execute(text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'afk_entries' 
                AND column_name = 'is_deleted';
            """))
            
            if not result.fetchone():
                logger.info("Adding is_deleted column to afk_entries table...")
                connection.execute(text("""
                    ALTER TABLE afk_entries 
                    ADD COLUMN is_deleted BOOLEAN NOT NULL DEFAULT FALSE;
                """))
                connection.commit()
                logger.info("Successfully added is_deleted column")
            else:
                logger.info("is_deleted column already exists")
                
    except Exception as e:
        logger.error(f"Error adding is_deleted column: {e}")
        raise

def migrate_data():
    """Migrate data from SQLite to PostgreSQL."""
    try:
        # First, add the new column
        add_is_deleted_column()
        
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
        
        # First, create a mapping of user_ids
        user_id_mapping = {}
        
        # Get unique users from afk_users table
        logger.info("Creating users from AFK entries...")
        sqlite_cursor.execute("""
            SELECT DISTINCT user_id, display_name, clan_role_id 
            FROM afk_users
        """)
        unique_users = sqlite_cursor.fetchall()
        
        for user_data in unique_users:
            old_user_id, display_name, clan_role_id = user_data
            
            # Check if user already exists
            existing_user = pg_session.execute(
                select(User).where(User.discord_id == str(old_user_id))
            ).scalar_one_or_none()
            
            if existing_user:
                logger.info(f"User with discord_id {old_user_id} already exists, skipping creation")
                user_id_mapping[old_user_id] = existing_user.id
                continue
            
            # Create new user
            user = User(
                discord_id=str(old_user_id),  # Use old user_id as discord_id
                username=display_name,  # Use display_name as username initially
                display_name=display_name,
                clan_role_id=str(clan_role_id) if clan_role_id else None
            )
            pg_session.add(user)
            pg_session.flush()  # Get the new user_id
            user_id_mapping[old_user_id] = user.id
        
        pg_session.commit()
        logger.info(f"Created {len(user_id_mapping)} users")
        
        # Migrate AFK entries
        logger.info("Migrating AFK entries...")
        sqlite_cursor.execute("""
            SELECT id, user_id, start_date, end_date, reason, 
                   is_active, created_at, ended_at
            FROM afk_users
        """)
        afk_entries = sqlite_cursor.fetchall()
        
        migrated_entries = 0
        for afk_data in afk_entries:
            (old_id, old_user_id, start_date, end_date, reason, 
             is_active, created_at, ended_at) = afk_data
            
            # Map old user_id to new user_id
            new_user_id = user_id_mapping.get(old_user_id)
            if not new_user_id:
                logger.warning(f"Skipping AFK entry {old_id}: User mapping not found for user_id {old_user_id}")
                continue
            
            # Convert string dates to datetime objects
            try:
                start_date = datetime.fromisoformat(start_date) if start_date else None
                end_date = datetime.fromisoformat(end_date) if end_date else None
                created_at = datetime.fromisoformat(created_at) if created_at else datetime.utcnow()
                ended_at = datetime.fromisoformat(ended_at) if ended_at else None
            except ValueError as e:
                logger.warning(f"Error parsing dates for AFK entry {old_id}: {e}")
                continue
            
            if not start_date or not end_date:
                logger.warning(f"Skipping AFK entry {old_id} due to missing dates")
                continue
            
            afk_entry = AFKEntry(
                user_id=new_user_id,
                start_date=start_date,
                end_date=end_date,
                reason=reason,
                is_active=bool(is_active),
                created_at=created_at,
                ended_at=ended_at
            )
            pg_session.add(afk_entry)
            migrated_entries += 1
        
        pg_session.commit()
        logger.info(f"Migrated {migrated_entries} AFK entries")
        
        # Close connections
        sqlite_conn.close()
        pg_session.close()
        
        logger.info("Migration completed successfully!")
        
    except Exception as e:
        logger.error(f"Error during migration: {e}")
        raise

def migrate():
    """Create all database tables."""
    logging.info("Starting database migration...")
    try:
        engine = create_engine(DATABASE_URL)
        Base.metadata.create_all(engine)
        logging.info("Database tables created successfully")
        
        # Migrate guild information
        migrate_guild_info(engine)
        
    except Exception as e:
        logging.error(f"Error during migration: {e}")
        raise

def migrate_guild_info(engine):
    """Migrate guild information from environment variables to database."""
    logging.info("Migrating guild information...")
    try:
        with Session(engine) as session:
            # Check if guild info already exists
            if session.query(GuildInfo).count() > 0:
                logging.info("Guild information already exists in database")
                return

            # Get guild information from environment variables
            guild_roles = {
                "GUILD_ROLE_ID_REQUIEM": ("Requiem", os.getenv("GUILD_ROLE_ID_REQUIEM")),
                "GUILD_ROLE_ID_REQUIEM_RISING": ("Requiem Rising", os.getenv("GUILD_ROLE_ID_REQUIEM_RISING")),
                "GUILD_ROLE_ID_REQUIEM_DAWN": ("Requiem Dawn", os.getenv("GUILD_ROLE_ID_REQUIEM_DAWN")),
                "GUILD_ROLE_ID_REQUIEM_HOPE": ("Requiem Hope", os.getenv("GUILD_ROLE_ID_REQUIEM_HOPE")),
            }

            # Add guild information to database
            for env_key, (name, role_id) in guild_roles.items():
                if role_id:
                    guild_info = GuildInfo(role_id=role_id, name=name)
                    session.add(guild_info)
                else:
                    logging.warning(f"Missing role ID for guild {name} ({env_key})")

            session.commit()
            logging.info("Guild information migrated successfully")

    except Exception as e:
        logging.error(f"Error migrating guild information: {e}")
        raise

if __name__ == "__main__":
    migrate() 