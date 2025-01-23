"""Script to add guild information to the database."""
import os
import logging
from dotenv import load_dotenv

from src.database.connection import get_db_session
from src.database.operations import add_guild_info

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

def add_guilds():
    """Add guild information to the database."""
    try:
        with get_db_session() as db:
            # Add Gruppe 9
            clan1_role_id = os.getenv("CLAN1_ROLE_ID")
            clan1_name = os.getenv("CLAN1_NAME", "Gruppe 9")
            if clan1_role_id:
                guild_info = add_guild_info(db, str(clan1_role_id), clan1_name)
                logger.info(f"Added/Updated guild: {guild_info.name} (Role ID: {guild_info.role_id})")
            
            # Add Requiem Moon
            clan2_role_id = os.getenv("CLAN2_ROLE_ID")
            clan2_name = os.getenv("CLAN2_NAME", "Requiem Moon")
            if clan2_role_id:
                guild_info = add_guild_info(db, str(clan2_role_id), clan2_name)
                logger.info(f"Added/Updated guild: {guild_info.name} (Role ID: {guild_info.role_id})")
            
    except Exception as e:
        logger.error(f"Error adding guild information: {e}")
        raise

if __name__ == "__main__":
    add_guilds() 