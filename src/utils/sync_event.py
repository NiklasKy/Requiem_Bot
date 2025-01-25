import os
import sys
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent.parent.parent
sys.path.append(str(project_root))

import logging
import asyncio
from src.database.connection import get_db_session
from src.database.models import RaidHelperEvent, RaidHelperSignup
from src.services.raidhelper import RaidHelperService

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

async def sync_event(event_id: str):
    """Sync a specific event and its signups from RaidHelper API and update database entries."""
    rh_service = RaidHelperService()
    
    # Fetch event details from API
    event_details = await rh_service.fetch_event_details(event_id)
    if not event_details:
        logging.error(f"Could not fetch event {event_id} from RaidHelper API")
        return
        
    with get_db_session() as session:
        # Create event data structure
        event_data = {
            "id": event_id,
            "title": event_details.get("title", ""),
            "description": event_details.get("description", ""),
            "leaderId": event_details.get("leaderId", ""),
            "leaderName": event_details.get("leaderName", ""),
            "channelId": event_details.get("channelId", ""),
            "channelName": event_details.get("channelName", ""),
            "startTime": event_details.get("startTime", ""),
            "endTime": event_details.get("endTime", ""),
            "closeTime": event_details.get("closeTime", ""),
            "lastUpdated": event_details.get("lastUpdated", ""),
            "templateId": event_details.get("templateId", ""),
            "signUpCount": len(event_details.get("signups", []))
        }
        
        # Update event in database
        event = await rh_service.create_or_update_raidhelper_event(event_data)
        if not event:
            logging.error(f"Failed to update event {event_id}")
            return

        # Delete existing signups for this event
        session.query(RaidHelperSignup).filter(RaidHelperSignup.event_id == event_id).delete()
        
        # Create new signups from API data
        for signup in event_details.get("signups", []):
            signup_data = {
                "event_id": event_id,
                "user_id": signup.get("userId", ""),
                "user_name": signup.get("userName", ""),
                "spec_name": signup.get("specName", ""),
                "class_name": signup.get("className", ""),
                "role": signup.get("role", ""),
                "status": signup.get("status", ""),
                "signup_time": signup.get("signupTime", ""),
                "tentative": signup.get("tentative", False)
            }
            new_signup = RaidHelperSignup(**signup_data)
            session.add(new_signup)
        
        try:
            session.commit()
            logging.info(f"Successfully synced event {event_id} and its signups from RaidHelper API")
        except Exception as e:
            session.rollback()
            logging.error(f"Failed to save signups for event {event_id}: {str(e)}")

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python sync_event.py <event_id>")
        sys.exit(1)
    
    event_id = sys.argv[1]
    asyncio.run(sync_event(event_id)) 