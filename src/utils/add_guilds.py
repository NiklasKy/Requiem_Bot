"""Script to add guild information to the database."""
import os
import logging
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.database.models import Base, GuildInfo

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

def get_db_session():
    """Create a database session."""
    DB_USER = os.getenv("DB_USER", "postgres")
    DB_PASSWORD = os.getenv("DB_PASSWORD", "")
    DB_HOST = os.getenv("DB_HOST", "localhost")
    DB_PORT = os.getenv("DB_PORT", "5432")
    DB_NAME = os.getenv("DB_NAME", "requiem_bot")
    
    DATABASE_URL = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    
    engine = create_engine(DATABASE_URL)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    return SessionLocal()

def add_guilds():
    """Add guild information to the database."""
    try:
        db = get_db_session()
        
        try:
            # Add Gruppe 9
            clan1_role_id = os.getenv("CLAN1_ROLE_ID")
            clan1_name = os.getenv("CLAN1_NAME", "Gruppe 9")
            if clan1_role_id:
                logger.info(f"Adding guild {clan1_name} with role ID {clan1_role_id}")
                guild_info = db.query(GuildInfo).filter(GuildInfo.role_id == str(clan1_role_id)).first()
                if guild_info:
                    guild_info.name = clan1_name
                    logger.info(f"Updated existing guild: {clan1_name}")
                else:
                    guild_info = GuildInfo(role_id=str(clan1_role_id), name=clan1_name)
                    db.add(guild_info)
                    logger.info(f"Added new guild: {clan1_name}")
            
            # Add Requiem Moon
            clan2_role_id = os.getenv("CLAN2_ROLE_ID")
            clan2_name = os.getenv("CLAN2_NAME", "Requiem Moon")
            if clan2_role_id:
                logger.info(f"Adding guild {clan2_name} with role ID {clan2_role_id}")
                guild_info = db.query(GuildInfo).filter(GuildInfo.role_id == str(clan2_role_id)).first()
                if guild_info:
                    guild_info.name = clan2_name
                    logger.info(f"Updated existing guild: {clan2_name}")
                else:
                    guild_info = GuildInfo(role_id=str(clan2_role_id), name=clan2_name)
                    db.add(guild_info)
                    logger.info(f"Added new guild: {clan2_name}")
            
            db.commit()
            logger.info("Successfully added/updated guild information")
            
        except Exception as e:
            db.rollback()
            logger.error(f"Error adding guild information: {e}")
            raise
        finally:
            db.close()
            
    except Exception as e:
        logger.error(f"Database connection error: {e}")
        raise

if __name__ == "__main__":
    add_guilds() 