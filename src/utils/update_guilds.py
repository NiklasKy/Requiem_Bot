import os
import sys
from pathlib import Path

# Add the project root to the Python path
project_root = Path(__file__).parent.parent.parent
sys.path.append(str(project_root))

from dotenv import load_dotenv
from src.database.connection import get_db_session
from src.database.operations import add_guild_info
import logging

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

def update_guild_names():
    # Load environment variables
    load_dotenv()
    
    # Get guild information from .env
    guilds = [
        {
            "role_id": os.getenv("CLAN1_ROLE_ID"),
            "name": os.getenv("CLAN1_NAME")
        },
        {
            "role_id": os.getenv("CLAN2_ROLE_ID"),
            "name": os.getenv("CLAN2_NAME")
        }
    ]
    
    # Update guild information in database
    with get_db_session() as db:
        for guild in guilds:
            if guild["role_id"] and guild["name"]:
                logging.info(f"Updating guild: {guild['name']} with role ID: {guild['role_id']}")
                add_guild_info(db, guild["role_id"], guild["name"])
            else:
                logging.warning(f"Missing information for guild: {guild}")

if __name__ == "__main__":
    update_guild_names() 