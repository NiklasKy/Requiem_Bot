"""Activity Tracker Service for RaidHelper events."""
import os
import logging
import asyncio
from datetime import datetime

from src.database.connection import get_db_session, wait_for_db
from src.database.models import RaidHelperEvent, RaidHelperSignup, User, GuildInfo
from src.services.raidhelper import RaidHelperService
from src.services.google_sheets import GoogleSheetsService

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

class ActivityTracker:
    """Service to track and process RaidHelper event activities."""
    
    def __init__(self):
        """Initialize the Activity Tracker service."""
        # Wait for database to be ready
        wait_for_db()
        logging.info("Database connection established")
        
        self.raidhelper = RaidHelperService()
        self.sheets_service = GoogleSheetsService()
        logging.info("Activity Tracker Service initialized")

    async def run(self):
        """Run the activity tracker service."""
        logging.info("Starting Activity Tracker Service")
        while True:
            try:
                await self.raidhelper.sync_active_events()
                await self.raidhelper.process_closed_events()
            except Exception as e:
                logging.error(f"Error in activity tracker: {e}")
            
            # Wait 5 minutes before next sync
            logging.info("Waiting 5 minutes before next sync")
            await asyncio.sleep(300)

async def main():
    """Main entry point for the Activity Tracker Service."""
    tracker = ActivityTracker()
    await tracker.run()

if __name__ == "__main__":
    asyncio.run(main()) 