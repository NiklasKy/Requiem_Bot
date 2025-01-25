import os
import sys
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent.parent.parent
sys.path.append(str(project_root))

import logging
from src.database.connection import get_db_session
from src.database.models import ProcessedEvent, RaidHelperEvent, RaidHelperSignup
from src.services.raidhelper import RaidHelperService
from src.services.google_sheets import GoogleSheetsService

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

def reprocess_event(event_id: str):
    """Remove event from processed_events and process it again."""
    with get_db_session() as session:
        # Remove from processed_events
        processed = session.query(ProcessedEvent).filter(ProcessedEvent.event_id == event_id).first()
        if processed:
            session.delete(processed)
            session.commit()
            logging.info(f"Removed event {event_id} from processed_events")
        else:
            logging.info(f"Event {event_id} was not in processed_events")
        
        # Get event details
        event = session.query(RaidHelperEvent).filter(RaidHelperEvent.id == event_id).first()
        if not event:
            logging.error(f"Event {event_id} not found in database")
            return
            
        # Get all signups for this event
        signups = session.query(RaidHelperSignup).filter(
            RaidHelperSignup.event_id == str(event_id)
        ).all()
        
        # Initialize services
        rh_service = RaidHelperService()
        
        # Process event with signups
        rh_service.process_closed_event(event, signups)
        logging.info(f"Successfully reprocessed event {event_id}")

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python reprocess_event.py <event_id>")
        sys.exit(1)
    
    event_id = sys.argv[1]
    reprocess_event(event_id) 