import os
import sys
from pathlib import Path
from datetime import datetime
import json

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

def convert_timestamp(ts):
    """Convert Unix timestamp to datetime object."""
    if not ts:
        return None
    try:
        return datetime.fromtimestamp(int(ts))
    except (ValueError, TypeError):
        return None

async def sync_event(event_id: str):
    """Sync a specific event and its signups from RaidHelper API and update database entries."""
    rh_service = RaidHelperService()
    
    # Fetch event details from API
    event_details = await rh_service.fetch_event_details(event_id)
    if not event_details:
        logging.error(f"Could not fetch event {event_id} from RaidHelper API")
        return
    
    # Debug: Print the structure of event_details
    logging.info("API Response Structure:")
    for key in event_details.keys():
        logging.info(f"Found key: {key}")
        if key == "classes":
            for class_info in event_details["classes"]:
                logging.info(f"Class: {class_info.get('name')} - {len(class_info.get('specs', []))} specs")
                if "signups" in class_info:
                    logging.info(f"Found {len(class_info['signups'])} signups in {class_info['name']}")
    
    # Extract signups from the response
    signups = event_details.get("signUps", [])
    logging.info(f"Found {len(signups)} signups in API response")
        
    with get_db_session() as session:
        # Get or create event in database
        event = session.query(RaidHelperEvent).filter(RaidHelperEvent.id == event_id).first()
        if not event:
            event = RaidHelperEvent()
            logging.info("Creating new event in database")
        else:
            logging.info("Updating existing event in database")
            
        # Update event data
        event.id = event_id
        event.title = event_details.get("title", "")
        event.description = event_details.get("description", "")
        event.leader_id = event_details.get("leaderId", "")
        event.leader_name = event_details.get("leaderName", "")
        event.channel_id = event_details.get("channelId", "")
        event.channel_name = event_details.get("channelName", "")
        event.start_time = convert_timestamp(event_details.get("startTime"))
        event.end_time = convert_timestamp(event_details.get("endTime"))
        event.close_time = convert_timestamp(event_details.get("closingTime"))
        event.last_updated = convert_timestamp(event_details.get("lastUpdated"))
        event.template_id = event_details.get("templateId", "")
        event.sign_up_count = len(signups)
        
        session.add(event)
        
        # Count existing signups
        existing_count = session.query(RaidHelperSignup).filter(RaidHelperSignup.event_id == event_id).count()
        logging.info(f"Found {existing_count} existing signups in database")
        
        # Delete existing signups for this event
        session.query(RaidHelperSignup).filter(RaidHelperSignup.event_id == event_id).delete()
        logging.info("Deleted existing signups from database")
        
        # Create new signups from API data
        for signup in signups:
            logging.info(f"Processing signup data: {json.dumps(signup, indent=2)}")
            signup_data = RaidHelperSignup(
                event_id=event_id,
                user_id=signup.get("userId", ""),
                user_name=signup.get("name", ""),
                spec_name=signup.get("specName", ""),
                class_name=signup.get("className", ""),
                role=signup.get("className", ""),  # Using className as role since that's what we have
                status=signup.get("status", ""),
                signup_time=convert_timestamp(signup.get("entryTime")),
                tentative=False  # Default to False as we don't have this info
            )
            session.add(signup_data)
        
        try:
            session.commit()
            new_count = session.query(RaidHelperSignup).filter(RaidHelperSignup.event_id == event_id).count()
            logging.info(f"Successfully synced event {event_id}")
            logging.info(f"Signups before: {existing_count}, Signups after: {new_count}")
        except Exception as e:
            session.rollback()
            logging.error(f"Failed to save event {event_id} and its signups: {str(e)}")

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python sync_event.py <event_id>")
        sys.exit(1)
    
    event_id = sys.argv[1]
    asyncio.run(sync_event(event_id)) 